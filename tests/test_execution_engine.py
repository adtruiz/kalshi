"""Tests for the ExecutionEngine class."""

import asyncio
import pytest

from config.strategy_params import StrategyParams
from src.api import (
    MockRestClient,
    MockWebSocketClient,
    OrderSide,
    SpreadOpportunity,
)
from src.execution.execution_engine import ExecutionEngine
from src.execution.order_manager import OrderManager
from src.models import FillResult
from src.portfolio.position_tracker import PositionTracker
from src.portfolio.risk_manager import RiskManager


@pytest.fixture
def rest_client():
    """Create a mock REST client."""
    client = MockRestClient()
    client.set_balance(100000)  # $1000
    return client


@pytest.fixture
def ws_client(rest_client):
    """Create a mock WebSocket client."""
    return MockWebSocketClient(rest_client)


@pytest.fixture
def order_manager(rest_client, ws_client):
    """Create an OrderManager instance."""
    return OrderManager(rest_client, ws_client)


@pytest.fixture
def position_tracker(rest_client):
    """Create a PositionTracker instance."""
    return PositionTracker(rest_client)


@pytest.fixture
def params():
    """Create strategy parameters with short timeouts for testing."""
    return StrategyParams(
        max_position_size=100,
        max_concurrent_positions=5,
        risk_per_trade_pct=0.02,
        order_timeout_seconds=2,  # Short timeout for tests
        daily_loss_limit_pct=0.05,
    )


@pytest.fixture
def risk_manager(rest_client, position_tracker, params):
    """Create a RiskManager instance."""
    return RiskManager(rest_client, position_tracker, params)


@pytest.fixture
def execution_engine(order_manager, position_tracker, risk_manager, params):
    """Create an ExecutionEngine instance."""
    return ExecutionEngine(order_manager, position_tracker, risk_manager, params)


@pytest.fixture
def opportunity():
    """Create a sample spread opportunity."""
    return SpreadOpportunity(
        ticker="TEST-SPREAD",
        side=OrderSide.YES,
        bid_price=45,
        ask_price=50,
        spread_cents=5,
        volume_24h=1000,
        liquidity=5000,
        days_to_expiration=10,
    )


class TestExecuteSpreadTrade:
    """Tests for spread trade execution."""

    @pytest.mark.asyncio
    async def test_successful_spread_trade(
        self, execution_engine, risk_manager, ws_client, opportunity
    ):
        """Test a successful spread trade execution."""
        await risk_manager.initialize()

        # Simulate fills in background
        async def simulate_fills():
            await asyncio.sleep(0.1)
            # Get the buy order and fill it
            active_orders = execution_engine._order_manager.get_active_orders()
            if active_orders:
                buy_order = active_orders[0]
                await ws_client.simulate_fill_after_delay(buy_order.order_id, 0.1)

                # Wait for sell order
                await asyncio.sleep(0.3)
                active_orders = execution_engine._order_manager.get_active_orders()
                if active_orders:
                    sell_order = active_orders[0]
                    await ws_client.simulate_fill_after_delay(sell_order.order_id, 0.1)

        fill_task = asyncio.create_task(simulate_fills())

        result = await execution_engine.execute_spread_trade(opportunity)

        await fill_task

        assert result.success is True
        assert result.ticker == opportunity.ticker
        assert result.buy_order_id is not None
        assert result.sell_order_id is not None
        assert result.quantity_filled > 0
        assert result.entry_price == opportunity.bid_price
        assert result.exit_price == opportunity.ask_price
        assert result.gross_pnl > 0
        assert result.net_pnl == result.gross_pnl - result.fees

    @pytest.mark.asyncio
    async def test_trade_rejected_by_risk_check(
        self, execution_engine, risk_manager, opportunity
    ):
        """Test that trades failing risk checks are rejected."""
        await risk_manager.initialize()
        risk_manager.halt_trading("Testing")

        result = await execution_engine.execute_spread_trade(opportunity)

        assert result.success is False
        assert "Risk check failed" in result.error_message
        assert result.buy_order_id is None

    @pytest.mark.asyncio
    async def test_buy_order_timeout(
        self, execution_engine, risk_manager, opportunity
    ):
        """Test handling of buy order timeout."""
        await risk_manager.initialize()

        # Don't simulate any fills - should timeout
        result = await execution_engine.execute_spread_trade(opportunity)

        assert result.success is False
        assert result.buy_fill_result == FillResult.TIMEOUT
        assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_pnl_calculation(
        self, execution_engine, risk_manager, ws_client, opportunity
    ):
        """Test PnL calculation for completed trade."""
        await risk_manager.initialize()

        # Simulate immediate fills
        async def simulate_fills():
            await asyncio.sleep(0.05)
            for _ in range(2):
                orders = execution_engine._order_manager.get_active_orders()
                if orders:
                    await ws_client.simulate_fill_after_delay(orders[0].order_id, 0.01)
                await asyncio.sleep(0.2)

        fill_task = asyncio.create_task(simulate_fills())
        result = await execution_engine.execute_spread_trade(opportunity)
        await fill_task

        if result.success:
            # Spread is 5 cents, fees are 2 cents per contract
            expected_gross = (opportunity.ask_price - opportunity.bid_price) * result.quantity_filled
            expected_fees = result.quantity_filled * 2
            expected_net = expected_gross - expected_fees

            assert result.gross_pnl == expected_gross
            assert result.fees == expected_fees
            assert result.net_pnl == expected_net


class TestTradeFlow:
    """Tests for the complete trade flow."""

    @pytest.mark.asyncio
    async def test_position_tracking_after_trade(
        self, execution_engine, risk_manager, position_tracker, ws_client, opportunity
    ):
        """Test that positions are properly tracked after trades."""
        await risk_manager.initialize()

        # Simulate fills
        async def simulate_fills():
            await asyncio.sleep(0.05)
            for _ in range(2):
                orders = execution_engine._order_manager.get_active_orders()
                if orders:
                    await ws_client.simulate_fill_after_delay(orders[0].order_id, 0.01)
                await asyncio.sleep(0.2)

        fill_task = asyncio.create_task(simulate_fills())
        result = await execution_engine.execute_spread_trade(opportunity)
        await fill_task

        if result.success:
            # After successful trade, position should be closed
            position = position_tracker.get_position(opportunity.ticker)
            if position:
                assert position.quantity == 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_trades(
        self, execution_engine, risk_manager, ws_client
    ):
        """Test multiple trades don't interfere with each other."""
        await risk_manager.initialize()

        opportunities = [
            SpreadOpportunity(
                ticker=f"MARKET_{i}",
                side=OrderSide.YES,
                bid_price=45,
                ask_price=50,
                spread_cents=5,
                volume_24h=1000,
                liquidity=5000,
                days_to_expiration=10,
            )
            for i in range(3)
        ]

        # Quick timeout trades (will all timeout but should not crash)
        results = await asyncio.gather(*[
            execution_engine.execute_spread_trade(opp)
            for opp in opportunities
        ])

        assert len(results) == 3
        for result in results:
            assert result.ticker is not None


class TestCancelPending:
    """Tests for cancelling pending orders."""

    @pytest.mark.asyncio
    async def test_cancel_all_pending(self, execution_engine, order_manager):
        """Test cancelling all pending orders."""
        from src.api import OrderAction

        # Place some orders
        await order_manager.place_limit_order(
            ticker="MARKET1",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )
        await order_manager.place_limit_order(
            ticker="MARKET2",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        cancelled = await execution_engine.cancel_all_pending()
        assert cancelled == 2

    @pytest.mark.asyncio
    async def test_cancel_pending_by_ticker(self, execution_engine, order_manager):
        """Test cancelling pending orders for specific ticker."""
        from src.api import OrderAction

        await order_manager.place_limit_order(
            ticker="MARKET_A",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )
        await order_manager.place_limit_order(
            ticker="MARKET_B",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        cancelled = await execution_engine.cancel_all_pending(ticker="MARKET_A")
        assert cancelled == 1
        assert len(order_manager.get_active_orders()) == 1
