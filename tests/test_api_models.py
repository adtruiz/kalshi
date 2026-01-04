"""Tests for API data models."""

from datetime import datetime, timedelta

import pytest

from src.api.models import Market, OrderBook, OrderBookLevel


class TestOrderBookLevel:
    """Tests for OrderBookLevel dataclass."""

    def test_create_level(self):
        """Test creating an order book level."""
        level = OrderBookLevel(price=50, quantity=100)

        assert level.price == 50
        assert level.quantity == 100


class TestOrderBook:
    """Tests for OrderBook dataclass."""

    def test_empty_orderbook(self):
        """Test empty orderbook properties."""
        orderbook = OrderBook()

        assert orderbook.best_yes_bid is None
        assert orderbook.best_yes_ask is None
        assert orderbook.spread is None
        assert orderbook.midpoint is None
        assert orderbook.yes_bid_depth == 0
        assert orderbook.yes_ask_depth == 0

    def test_best_yes_bid(self):
        """Test best bid calculation."""
        orderbook = OrderBook(
            yes_bids=[
                OrderBookLevel(price=45, quantity=100),
                OrderBookLevel(price=50, quantity=50),
                OrderBookLevel(price=40, quantity=200),
            ]
        )

        assert orderbook.best_yes_bid == 50

    def test_best_yes_ask(self):
        """Test best ask calculation."""
        orderbook = OrderBook(
            yes_asks=[
                OrderBookLevel(price=55, quantity=100),
                OrderBookLevel(price=52, quantity=50),
                OrderBookLevel(price=60, quantity=200),
            ]
        )

        assert orderbook.best_yes_ask == 52

    def test_spread(self):
        """Test spread calculation."""
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=45, quantity=100)],
            yes_asks=[OrderBookLevel(price=55, quantity=100)],
        )

        assert orderbook.spread == 10

    def test_midpoint(self):
        """Test midpoint calculation."""
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=40, quantity=100)],
            yes_asks=[OrderBookLevel(price=60, quantity=100)],
        )

        assert orderbook.midpoint == 50.0

    def test_yes_bid_depth(self):
        """Test bid depth calculation."""
        orderbook = OrderBook(
            yes_bids=[
                OrderBookLevel(price=45, quantity=100),
                OrderBookLevel(price=44, quantity=200),
                OrderBookLevel(price=43, quantity=300),
            ]
        )

        assert orderbook.yes_bid_depth == 600

    def test_yes_ask_depth(self):
        """Test ask depth calculation."""
        orderbook = OrderBook(
            yes_asks=[
                OrderBookLevel(price=55, quantity=50),
                OrderBookLevel(price=56, quantity=150),
            ]
        )

        assert orderbook.yes_ask_depth == 200

    def test_spread_with_only_bids(self):
        """Test spread is None with only bids."""
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=45, quantity=100)],
        )

        assert orderbook.spread is None

    def test_spread_with_only_asks(self):
        """Test spread is None with only asks."""
        orderbook = OrderBook(
            yes_asks=[OrderBookLevel(price=55, quantity=100)],
        )

        assert orderbook.spread is None


class TestMarket:
    """Tests for Market dataclass."""

    def test_create_market(self):
        """Test creating a market."""
        now = datetime.utcnow()
        expiration = now + timedelta(days=10)

        market = Market(
            ticker="TEST-TICKER",
            title="Test Market",
            status="active",
            expiration_time=expiration,
            close_time=expiration,
            volume_24h=500,
            liquidity=5000,
        )

        assert market.ticker == "TEST-TICKER"
        assert market.title == "Test Market"
        assert market.status == "active"
        assert market.is_active is True

    def test_is_active_false(self):
        """Test is_active returns False for non-active markets."""
        market = Market(
            ticker="TEST",
            title="Test",
            status="closed",
            expiration_time=datetime.utcnow(),
            close_time=datetime.utcnow(),
            volume_24h=0,
            liquidity=0,
        )

        assert market.is_active is False

    def test_days_to_expiration(self):
        """Test days to expiration calculation."""
        now = datetime.utcnow()
        market = Market(
            ticker="TEST",
            title="Test",
            status="active",
            expiration_time=now + timedelta(days=10, hours=12),
            close_time=now + timedelta(days=10, hours=12),
            volume_24h=500,
            liquidity=5000,
        )

        days = market.days_to_expiration(now)

        assert days == pytest.approx(10.5, rel=0.01)

    def test_days_to_expiration_past(self):
        """Test negative days for past expiration."""
        now = datetime.utcnow()
        market = Market(
            ticker="TEST",
            title="Test",
            status="closed",
            expiration_time=now - timedelta(days=2),
            close_time=now - timedelta(days=2),
            volume_24h=0,
            liquidity=0,
        )

        days = market.days_to_expiration(now)

        assert days < 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        expiration = datetime(2024, 1, 15, 12, 0, 0)

        market = Market(
            ticker="TEST",
            title="Test Market",
            status="active",
            expiration_time=expiration,
            close_time=expiration,
            volume_24h=500,
            liquidity=5000,
            yes_bid=45,
            yes_ask=55,
            last_price=50,
            open_interest=1000,
            category="crypto",
            event_ticker="EVENT",
        )

        result = market.to_dict()

        assert result["ticker"] == "TEST"
        assert result["title"] == "Test Market"
        assert result["status"] == "active"
        assert result["expiration_time"] == "2024-01-15T12:00:00"
        assert result["volume_24h"] == 500
        assert result["yes_bid"] == 45
        assert result["yes_ask"] == 55

    def test_optional_fields(self):
        """Test that optional fields have correct defaults."""
        market = Market(
            ticker="TEST",
            title="Test",
            status="active",
            expiration_time=datetime.utcnow(),
            close_time=datetime.utcnow(),
            volume_24h=500,
            liquidity=5000,
        )

        assert market.yes_bid is None
        assert market.yes_ask is None
        assert market.last_price is None
        assert market.open_interest == 0
        assert market.category == ""
        assert market.event_ticker == ""
