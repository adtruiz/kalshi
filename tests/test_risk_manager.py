"""Tests for the RiskManager class."""

import pytest

from config.strategy_params import StrategyParams
from src.api import MockRestClient, OrderSide, SpreadOpportunity
from src.models import PositionStatus, TrackedPosition
from src.portfolio.position_tracker import PositionTracker
from src.portfolio.risk_manager import RiskManager


@pytest.fixture
def rest_client():
    """Create a mock REST client."""
    client = MockRestClient()
    client.set_balance(100000)  # $1000
    return client


@pytest.fixture
def position_tracker(rest_client):
    """Create a PositionTracker instance."""
    return PositionTracker(rest_client)


@pytest.fixture
def params():
    """Create strategy parameters."""
    return StrategyParams(
        max_position_size=100,
        max_concurrent_positions=5,
        risk_per_trade_pct=0.02,
        daily_loss_limit_pct=0.05,
        position_stop_loss_pct=0.10,
    )


@pytest.fixture
def risk_manager(rest_client, position_tracker, params):
    """Create a RiskManager instance."""
    return RiskManager(rest_client, position_tracker, params)


@pytest.fixture
def opportunity():
    """Create a sample spread opportunity."""
    return SpreadOpportunity(
        ticker="TEST-MARKET",
        side=OrderSide.YES,
        bid_price=45,
        ask_price=50,
        spread_cents=5,
        volume_24h=1000,
        liquidity=5000,
        days_to_expiration=10,
    )


class TestCanOpenPosition:
    """Tests for position opening checks."""

    @pytest.mark.asyncio
    async def test_can_open_position_success(self, risk_manager, opportunity):
        """Test that a valid position can be opened."""
        await risk_manager.initialize()
        can_trade, reason = await risk_manager.can_open_position(opportunity, 10)

        assert can_trade is True
        assert reason == "OK"

    @pytest.mark.asyncio
    async def test_cannot_exceed_max_positions(
        self, risk_manager, position_tracker, opportunity, params
    ):
        """Test that max concurrent positions is enforced."""
        await risk_manager.initialize()

        # Add positions up to the limit
        for i in range(params.max_concurrent_positions):
            position_tracker.update_position(
                ticker=f"MARKET_{i}",
                side=OrderSide.YES,
                qty_change=10,
                price=50,
            )

        can_trade, reason = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is False
        assert "Max concurrent positions" in reason

    @pytest.mark.asyncio
    async def test_cannot_open_duplicate_position(
        self, risk_manager, position_tracker, opportunity
    ):
        """Test that duplicate positions are prevented."""
        await risk_manager.initialize()

        # Add existing position for the same ticker
        position_tracker.update_position(
            ticker=opportunity.ticker,
            side=OrderSide.YES,
            qty_change=10,
            price=50,
        )

        can_trade, reason = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is False
        assert "Already have position" in reason

    @pytest.mark.asyncio
    async def test_cannot_exceed_max_position_size(
        self, risk_manager, opportunity, params
    ):
        """Test that max position size is enforced."""
        await risk_manager.initialize()

        can_trade, reason = await risk_manager.can_open_position(
            opportunity, params.max_position_size + 1
        )
        assert can_trade is False
        assert "exceeds max position size" in reason

    @pytest.mark.asyncio
    async def test_insufficient_balance(self, risk_manager, rest_client, opportunity):
        """Test that insufficient balance is caught."""
        await risk_manager.initialize()
        rest_client.set_balance(100)  # Only $1

        can_trade, reason = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is False
        assert "Insufficient balance" in reason

    @pytest.mark.asyncio
    async def test_trading_halted(self, risk_manager, opportunity):
        """Test that halted trading prevents new positions."""
        await risk_manager.initialize()
        risk_manager.halt_trading("Manual halt for testing")

        can_trade, reason = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is False
        assert "Trading halted" in reason


class TestPositionSizing:
    """Tests for position size calculation."""

    @pytest.mark.asyncio
    async def test_calculate_position_size_basic(self, risk_manager, opportunity):
        """Test basic position size calculation."""
        await risk_manager.initialize()

        # With $1000 balance and 2% risk
        # Risk amount = $20 = 2000 cents
        # Max loss per contract = 45 cents (bid price)
        # Base size = 2000 / 45 = 44 contracts
        size = risk_manager.calculate_position_size(opportunity, 100000)

        assert size > 0
        assert size <= 100  # Max position size

    @pytest.mark.asyncio
    async def test_position_size_respects_max(self, risk_manager, opportunity, params):
        """Test that position size doesn't exceed maximum."""
        await risk_manager.initialize()

        size = risk_manager.calculate_position_size(opportunity, 10000000)  # $100k
        assert size <= params.max_position_size

    @pytest.mark.asyncio
    async def test_position_size_respects_balance(self, risk_manager, opportunity):
        """Test that position size doesn't exceed balance."""
        await risk_manager.initialize()

        small_balance = 100  # $1 = 100 cents
        size = risk_manager.calculate_position_size(opportunity, small_balance)

        cost = opportunity.bid_price * size
        assert cost <= small_balance

    @pytest.mark.asyncio
    async def test_position_size_minimum_one(self, risk_manager, opportunity):
        """Test that position size is at least 1."""
        await risk_manager.initialize()

        size = risk_manager.calculate_position_size(opportunity, 100)
        assert size >= 1


class TestShouldExitPosition:
    """Tests for position exit checks."""

    def test_should_exit_on_stop_loss(self, risk_manager, params):
        """Test stop loss trigger."""
        position = TrackedPosition(
            ticker="TEST",
            side=OrderSide.YES,
            quantity=10,
            avg_entry_price=50,
            current_price=40,  # 20% loss
        )
        position._calculate_pnl()

        should_exit, reason = risk_manager.should_exit_position(position)
        assert should_exit is True
        assert "Stop loss" in reason

    def test_should_not_exit_small_loss(self, risk_manager, params):
        """Test that small losses don't trigger exit."""
        position = TrackedPosition(
            ticker="TEST",
            side=OrderSide.YES,
            quantity=10,
            avg_entry_price=50,
            current_price=48,  # 4% loss
        )
        position._calculate_pnl()

        should_exit, reason = risk_manager.should_exit_position(position)
        assert should_exit is False

    def test_should_not_exit_profit(self, risk_manager):
        """Test that profitable positions don't trigger exit."""
        position = TrackedPosition(
            ticker="TEST",
            side=OrderSide.YES,
            quantity=10,
            avg_entry_price=50,
            current_price=60,  # Profit
        )
        position._calculate_pnl()

        should_exit, reason = risk_manager.should_exit_position(position)
        assert should_exit is False


class TestTradingHalt:
    """Tests for trading halt functionality."""

    @pytest.mark.asyncio
    async def test_halt_and_resume(self, risk_manager, opportunity):
        """Test manual halt and resume."""
        await risk_manager.initialize()

        # Should be able to trade initially
        can_trade, _ = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is True

        # Halt trading
        risk_manager.halt_trading("Testing halt")
        assert risk_manager.is_trading_halted is True
        assert risk_manager.halt_reason == "Testing halt"

        can_trade, _ = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is False

        # Resume trading
        risk_manager.resume_trading()
        assert risk_manager.is_trading_halted is False

        can_trade, _ = await risk_manager.can_open_position(opportunity, 10)
        assert can_trade is True

    def test_reset_daily_limits(self, risk_manager):
        """Test daily limit reset."""
        risk_manager.halt_trading("Daily loss")
        risk_manager.reset_daily_limits()

        assert risk_manager.is_trading_halted is False
