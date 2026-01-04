"""Position tracking for the portfolio management system."""

from datetime import datetime
from typing import Dict, List, Optional

from src.api import MockRestClient, OrderSide, Position
from src.models import PositionStatus, TrackedPosition
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.position_tracker")


class PositionTracker:
    """
    Tracks all open positions and calculates PnL.

    Maintains an internal representation of positions that syncs
    with the API but also tracks additional metadata like entry time
    and average entry price.
    """

    def __init__(self, rest_client: MockRestClient):
        self._rest_client = rest_client
        self._positions: Dict[str, TrackedPosition] = {}
        self._daily_pnl: int = 0
        self._daily_pnl_reset: datetime = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    async def sync_positions(self):
        """
        Sync positions with the API.

        Fetches current positions from the API and updates
        internal tracking state.
        """
        logger.info("Syncing positions with API")

        try:
            api_positions = await self._rest_client.get_positions()

            # Update existing positions and add new ones
            api_tickers = set()
            for pos in api_positions:
                api_tickers.add(pos.ticker)

                if pos.market_exposure == 0:
                    # Position closed
                    if pos.ticker in self._positions:
                        tracked = self._positions[pos.ticker]
                        tracked.status = PositionStatus.CLOSED
                        logger.info(f"Position closed: {pos.ticker}")
                    continue

                if pos.ticker in self._positions:
                    # Update existing position
                    tracked = self._positions[pos.ticker]
                    # Note: API doesn't provide avg price, so we keep our calculated value
                    if pos.market_exposure > 0:
                        tracked.side = OrderSide.YES
                        tracked.quantity = pos.market_exposure
                    else:
                        tracked.side = OrderSide.NO
                        tracked.quantity = abs(pos.market_exposure)
                else:
                    # New position from API (e.g., from manual trade)
                    side = OrderSide.YES if pos.market_exposure > 0 else OrderSide.NO
                    qty = abs(pos.market_exposure)

                    self._positions[pos.ticker] = TrackedPosition(
                        ticker=pos.ticker,
                        side=side,
                        quantity=qty,
                        avg_entry_price=50,  # Default when unknown
                        current_price=50,
                    )
                    logger.info(f"New position detected: {pos.ticker} {side.value} x{qty}")

            # Check for positions that no longer exist in API
            for ticker in list(self._positions.keys()):
                if ticker not in api_tickers:
                    tracked = self._positions[ticker]
                    if tracked.status != PositionStatus.CLOSED:
                        tracked.status = PositionStatus.CLOSED
                        logger.info(f"Position no longer in API: {ticker}")

            logger.info(f"Position sync complete. {len(self._positions)} tracked positions")

        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")
            raise

    def update_position(
        self,
        ticker: str,
        side: OrderSide,
        qty_change: int,
        price: int,
    ):
        """
        Update a position after a fill.

        Args:
            ticker: Market ticker
            side: YES or NO
            qty_change: Positive for adding, negative for reducing
            price: Fill price in cents
        """
        logger.debug(
            f"Updating position: {ticker} {side.value} qty_change={qty_change} price={price}"
        )

        if ticker not in self._positions:
            if qty_change <= 0:
                logger.warning(f"Cannot reduce non-existent position: {ticker}")
                return

            # Create new position
            self._positions[ticker] = TrackedPosition(
                ticker=ticker,
                side=side,
                quantity=qty_change,
                avg_entry_price=price,
                current_price=price,
            )
            logger.info(f"New position opened: {ticker} {side.value} x{qty_change} @ {price}c")
            return

        tracked = self._positions[ticker]

        if qty_change > 0:
            # Adding to position
            if tracked.side != side:
                # Different side - this would be closing the opposite side
                pnl = tracked.reduce_position(qty_change, price)
                self._update_daily_pnl(pnl)
                logger.info(f"Position reduced (opposite side): {ticker} realized PnL={pnl}c")
            else:
                tracked.add_to_position(qty_change, price)
                logger.info(f"Position increased: {ticker} now {tracked.quantity} @ {tracked.avg_entry_price}c avg")
        else:
            # Reducing position
            pnl = tracked.reduce_position(abs(qty_change), price)
            self._update_daily_pnl(pnl)
            logger.info(f"Position reduced: {ticker} realized PnL={pnl}c, remaining={tracked.quantity}")

            if tracked.quantity == 0:
                tracked.status = PositionStatus.CLOSED

    def _update_daily_pnl(self, pnl: int):
        """Update daily PnL tracking."""
        # Reset if new day
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if today > self._daily_pnl_reset:
            self._daily_pnl = 0
            self._daily_pnl_reset = today

        self._daily_pnl += pnl

    def get_position(self, ticker: str) -> Optional[TrackedPosition]:
        """Get a tracked position by ticker."""
        return self._positions.get(ticker)

    def get_all_positions(self) -> List[TrackedPosition]:
        """Get all tracked positions."""
        return list(self._positions.values())

    def get_open_positions(self) -> List[TrackedPosition]:
        """Get all open (non-closed) positions."""
        return [
            p for p in self._positions.values()
            if p.status != PositionStatus.CLOSED
        ]

    def calculate_total_pnl(self) -> Dict[str, int]:
        """
        Calculate total PnL across all positions.

        Returns:
            Dict with 'realized', 'unrealized', and 'total' PnL in cents
        """
        realized = 0
        unrealized = 0

        for pos in self._positions.values():
            realized += pos.realized_pnl
            unrealized += pos.unrealized_pnl

        return {
            "realized": realized,
            "unrealized": unrealized,
            "total": realized + unrealized,
        }

    def get_daily_pnl(self) -> int:
        """Get today's realized PnL in cents."""
        # Reset if new day
        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if today > self._daily_pnl_reset:
            self._daily_pnl = 0
            self._daily_pnl_reset = today

        return self._daily_pnl

    def get_position_count(self) -> int:
        """Get the number of open positions."""
        return len(self.get_open_positions())

    def update_price(self, ticker: str, price: int):
        """Update the current price for a position."""
        if ticker in self._positions:
            self._positions[ticker].update_price(price)
