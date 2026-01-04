"""Execution engine for spread arbitrage trades."""

import asyncio
import time
from typing import Optional

from config.strategy_params import StrategyParams
from src.api import MockRestClient, OrderAction, OrderSide, SpreadOpportunity
from src.execution.order_manager import OrderManager
from src.models import FillResult, TradeResult
from src.portfolio.position_tracker import PositionTracker
from src.portfolio.risk_manager import RiskManager
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.execution_engine")


class ExecutionEngine:
    """
    Executes spread arbitrage trades.

    Orchestrates the full trade flow:
    1. Risk check
    2. Position sizing
    3. Buy order placement and fill
    4. Sell order placement and fill
    5. PnL calculation
    """

    def __init__(
        self,
        order_manager: OrderManager,
        position_tracker: PositionTracker,
        risk_manager: RiskManager,
        params: StrategyParams,
    ):
        self._order_manager = order_manager
        self._position_tracker = position_tracker
        self._risk_manager = risk_manager
        self._params = params
        self._active_trades: dict = {}

    async def execute_spread_trade(
        self,
        opportunity: SpreadOpportunity,
    ) -> TradeResult:
        """
        Execute a spread arbitrage trade.

        Trade flow:
        1. Risk check: can_open_position()
        2. Calculate position size
        3. Place BUY limit at bid price
        4. Wait for fill (timeout: 5 min)
        5. Place SELL limit at ask price
        6. Wait for sell fill
        7. Return TradeResult with profit/loss

        Args:
            opportunity: The spread opportunity to trade

        Returns:
            TradeResult with trade outcome
        """
        start_time = time.time()
        ticker = opportunity.ticker

        logger.info(
            f"Executing spread trade: {ticker} "
            f"bid={opportunity.bid_price}c ask={opportunity.ask_price}c "
            f"spread={opportunity.spread_cents}c"
        )

        result = TradeResult(
            success=False,
            ticker=ticker,
        )

        try:
            # Step 1: Get balance and calculate position size
            balance = await self._order_manager._rest_client.get_balance()
            size = self._risk_manager.calculate_position_size(
                opportunity, balance.available_balance
            )

            if size <= 0:
                result.error_message = "Position size calculated as 0"
                return result

            # Step 2: Risk check
            can_trade, reason = await self._risk_manager.can_open_position(
                opportunity, size
            )

            if not can_trade:
                logger.warning(f"Risk check failed: {reason}")
                result.error_message = f"Risk check failed: {reason}"
                return result

            logger.info(f"Risk check passed. Position size: {size}")

            # Step 3: Place BUY order at bid price
            buy_order = await self._order_manager.place_limit_order(
                ticker=ticker,
                side=opportunity.side,
                action=OrderAction.BUY,
                price=opportunity.bid_price,
                count=size,
            )
            result.buy_order_id = buy_order.order_id

            # Step 4: Wait for buy fill
            logger.info(f"Waiting for buy fill: {buy_order.order_id}")
            buy_result = await self._order_manager.wait_for_fill(
                buy_order.order_id,
                timeout_seconds=self._params.order_timeout_seconds,
            )
            result.buy_fill_result = buy_result

            if buy_result == FillResult.TIMEOUT:
                logger.warning("Buy order timed out, cancelling")
                await self._order_manager.cancel_order(buy_order.order_id)

                # Check for partial fill
                buy_order = self._order_manager.get_order(buy_order.order_id)
                if buy_order and buy_order.filled_count > 0:
                    # Handle partial fill - try to exit at market
                    result.quantity_filled = buy_order.filled_count
                    result.entry_price = opportunity.bid_price
                    result = await self._exit_partial_position(result, opportunity, buy_order.filled_count)
                else:
                    result.error_message = "Buy order timed out with no fill"
                return result

            if buy_result == FillResult.CANCELLED:
                result.error_message = "Buy order was cancelled"
                return result

            if buy_result == FillResult.ERROR:
                result.error_message = "Buy order encountered an error"
                return result

            # Get actual fill details
            buy_order = self._order_manager.get_order(buy_order.order_id)
            filled_qty = buy_order.filled_count if buy_order else size

            result.quantity_filled = filled_qty
            result.entry_price = opportunity.bid_price

            # Update position tracker
            self._position_tracker.update_position(
                ticker=ticker,
                side=opportunity.side,
                qty_change=filled_qty,
                price=opportunity.bid_price,
            )

            logger.info(f"Buy filled: {filled_qty} contracts @ {opportunity.bid_price}c")

            # Step 5: Place SELL order at ask price
            sell_order = await self._order_manager.place_limit_order(
                ticker=ticker,
                side=opportunity.side,
                action=OrderAction.SELL,
                price=opportunity.ask_price,
                count=filled_qty,
            )
            result.sell_order_id = sell_order.order_id

            # Step 6: Wait for sell fill
            logger.info(f"Waiting for sell fill: {sell_order.order_id}")
            sell_result = await self._order_manager.wait_for_fill(
                sell_order.order_id,
                timeout_seconds=self._params.order_timeout_seconds,
            )
            result.sell_fill_result = sell_result

            if sell_result == FillResult.TIMEOUT:
                logger.warning("Sell order timed out")
                await self._order_manager.cancel_order(sell_order.order_id)

                sell_order = self._order_manager.get_order(sell_order.order_id)
                if sell_order and sell_order.filled_count > 0:
                    # Partial sell - update result
                    sold_qty = sell_order.filled_count
                    result.exit_price = opportunity.ask_price
                    result = self._calculate_pnl(result, sold_qty, opportunity)
                    result.error_message = f"Partial sell: {sold_qty}/{filled_qty} contracts"
                else:
                    result.error_message = "Sell order timed out - position still open"
                return result

            if sell_result in (FillResult.CANCELLED, FillResult.ERROR):
                result.error_message = f"Sell order {sell_result.value} - position still open"
                return result

            # Step 7: Calculate final PnL
            result.exit_price = opportunity.ask_price
            result = self._calculate_pnl(result, filled_qty, opportunity)

            # Update position tracker for the sell
            self._position_tracker.update_position(
                ticker=ticker,
                side=opportunity.side,
                qty_change=-filled_qty,
                price=opportunity.ask_price,
            )

            result.success = True
            logger.info(
                f"Trade completed: {ticker} net_pnl=${result.net_pnl/100:.2f} "
                f"({result.quantity_filled} contracts)"
            )

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            result.error_message = str(e)

        finally:
            result.duration_seconds = time.time() - start_time

        return result

    def _calculate_pnl(
        self,
        result: TradeResult,
        quantity: int,
        opportunity: SpreadOpportunity,
    ) -> TradeResult:
        """Calculate PnL for a completed trade."""
        # Gross PnL = (exit - entry) * quantity
        result.gross_pnl = (result.exit_price - result.entry_price) * quantity

        # Fees: 1 cent per contract per side = 2 cents per round trip
        result.fees = quantity * 2

        # Net PnL
        result.net_pnl = result.gross_pnl - result.fees

        return result

    async def _exit_partial_position(
        self,
        result: TradeResult,
        opportunity: SpreadOpportunity,
        quantity: int,
    ) -> TradeResult:
        """
        Exit a partial position from a failed trade.

        Places a sell order to close out a partial buy fill.
        """
        logger.info(f"Exiting partial position: {quantity} contracts")

        # Update position tracker for the partial buy
        self._position_tracker.update_position(
            ticker=opportunity.ticker,
            side=opportunity.side,
            qty_change=quantity,
            price=opportunity.bid_price,
        )

        try:
            # Place sell order at current ask to exit quickly
            sell_order = await self._order_manager.place_limit_order(
                ticker=opportunity.ticker,
                side=opportunity.side,
                action=OrderAction.SELL,
                price=opportunity.ask_price,
                count=quantity,
            )
            result.sell_order_id = sell_order.order_id

            # Wait for sell with extended timeout
            sell_result = await self._order_manager.wait_for_fill(
                sell_order.order_id,
                timeout_seconds=self._params.order_timeout_seconds * 2,
            )
            result.sell_fill_result = sell_result

            if sell_result == FillResult.FILLED:
                result.exit_price = opportunity.ask_price
                result = self._calculate_pnl(result, quantity, opportunity)

                self._position_tracker.update_position(
                    ticker=opportunity.ticker,
                    side=opportunity.side,
                    qty_change=-quantity,
                    price=opportunity.ask_price,
                )
            else:
                result.error_message = "Failed to exit partial position"

        except Exception as e:
            logger.error(f"Failed to exit partial position: {e}")
            result.error_message = f"Failed to exit partial: {e}"

        return result

    async def cancel_all_pending(self, ticker: Optional[str] = None) -> int:
        """Cancel all pending orders."""
        return await self._order_manager.cancel_all_orders(ticker)
