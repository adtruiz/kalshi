"""Tests for the PositionTracker class."""

import pytest

from src.api import MockRestClient, OrderSide
from src.models import PositionStatus
from src.portfolio.position_tracker import PositionTracker


@pytest.fixture
def rest_client():
    """Create a mock REST client."""
    return MockRestClient()


@pytest.fixture
def position_tracker(rest_client):
    """Create a PositionTracker instance."""
    return PositionTracker(rest_client)


class TestPositionUpdates:
    """Tests for position update functionality."""

    def test_open_new_position(self, position_tracker):
        """Test opening a new position."""
        position_tracker.update_position(
            ticker="TEST-MARKET",
            side=OrderSide.YES,
            qty_change=10,
            price=45,
        )

        position = position_tracker.get_position("TEST-MARKET")
        assert position is not None
        assert position.ticker == "TEST-MARKET"
        assert position.side == OrderSide.YES
        assert position.quantity == 10
        assert position.avg_entry_price == 45
        assert position.status == PositionStatus.OPEN

    def test_add_to_position(self, position_tracker):
        """Test adding to an existing position."""
        # Open position
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=40,
        )

        # Add more
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )

        position = position_tracker.get_position("TEST")
        assert position.quantity == 20
        assert position.avg_entry_price == 45  # (40*10 + 50*10) / 20

    def test_reduce_position(self, position_tracker):
        """Test reducing a position."""
        # Open position
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=40,
        )

        # Reduce
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=-5,
            price=50,  # Sell at profit
        )

        position = position_tracker.get_position("TEST")
        assert position.quantity == 5
        assert position.realized_pnl == 50  # (50-40) * 5 = 50 cents

    def test_close_position(self, position_tracker):
        """Test closing a position completely."""
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=40,
        )

        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=-10,
            price=50,
        )

        position = position_tracker.get_position("TEST")
        assert position.quantity == 0
        assert position.status == PositionStatus.CLOSED
        assert position.realized_pnl == 100  # (50-40) * 10


class TestPnLCalculation:
    """Tests for PnL calculation."""

    def test_unrealized_pnl_long_yes(self, position_tracker):
        """Test unrealized PnL for long YES position."""
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=40,
        )

        position = position_tracker.get_position("TEST")
        position.update_price(50)  # Price went up

        assert position.unrealized_pnl == 100  # (50-40) * 10

    def test_unrealized_pnl_long_no(self, position_tracker):
        """Test unrealized PnL for long NO position."""
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.NO,
            qty_change=10,
            price=60,
        )

        position = position_tracker.get_position("TEST")
        position.update_price(50)  # Price of YES went down (NO is profitable)

        assert position.unrealized_pnl == 100  # (60-50) * 10

    def test_total_pnl_calculation(self, position_tracker):
        """Test total PnL across all positions."""
        # Position 1: realized profit
        position_tracker.update_position(
            ticker="MARKET1",
            side=OrderSide.YES,
            qty_change=10,
            price=40,
        )
        position_tracker.update_position(
            ticker="MARKET1",
            side=OrderSide.YES,
            qty_change=-10,
            price=50,
        )

        # Position 2: open with unrealized loss
        position_tracker.update_position(
            ticker="MARKET2",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )
        position_tracker.get_position("MARKET2").update_price(45)

        pnl = position_tracker.calculate_total_pnl()
        assert pnl["realized"] == 100  # From MARKET1
        assert pnl["unrealized"] == -50  # From MARKET2
        assert pnl["total"] == 50


class TestPositionQueries:
    """Tests for position query methods."""

    def test_get_all_positions(self, position_tracker):
        """Test getting all positions."""
        for i in range(3):
            position_tracker.update_position(
                ticker=f"MARKET_{i}",
                side=OrderSide.YES,
                qty_change=10,
                price=50,
            )

        positions = position_tracker.get_all_positions()
        assert len(positions) == 3

    def test_get_open_positions(self, position_tracker):
        """Test getting only open positions."""
        # Open position
        position_tracker.update_position(
            ticker="MARKET_OPEN",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )

        # Closed position
        position_tracker.update_position(
            ticker="MARKET_CLOSED",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )
        position_tracker.update_position(
            ticker="MARKET_CLOSED",
            side=OrderSide.YES,
            qty_change=-10,
            price=50,
        )

        open_positions = position_tracker.get_open_positions()
        assert len(open_positions) == 1
        assert open_positions[0].ticker == "MARKET_OPEN"

    def test_get_position_count(self, position_tracker):
        """Test position count."""
        assert position_tracker.get_position_count() == 0

        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )

        assert position_tracker.get_position_count() == 1


class TestDailyPnL:
    """Tests for daily PnL tracking."""

    def test_daily_pnl_tracking(self, position_tracker):
        """Test that daily PnL is tracked."""
        # Open and close position with profit
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=40,
        )
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=-10,
            price=50,
        )

        assert position_tracker.get_daily_pnl() == 100

    def test_daily_pnl_loss(self, position_tracker):
        """Test daily PnL with loss."""
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=-10,
            price=40,  # Sell at loss
        )

        assert position_tracker.get_daily_pnl() == -100


class TestPriceUpdates:
    """Tests for price update functionality."""

    def test_update_price(self, position_tracker):
        """Test updating position price."""
        position_tracker.update_position(
            ticker="TEST",
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )

        position_tracker.update_price("TEST", 60)
        position = position_tracker.get_position("TEST")

        assert position.current_price == 60
        assert position.unrealized_pnl == 100  # (60-50) * 10

    def test_update_price_nonexistent(self, position_tracker):
        """Test updating price for non-existent position."""
        # Should not raise
        position_tracker.update_price("NONEXISTENT", 50)
