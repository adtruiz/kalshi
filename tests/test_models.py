"""Tests for data models."""

from datetime import datetime

import pytest

from src.models import (
    Market,
    MarketStatus,
    Order,
    OrderAction,
    OrderBook,
    OrderBookLevel,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)


class TestMarket:
    """Tests for Market model."""

    def test_market_creation(self):
        """Test basic market creation."""
        market = Market(
            ticker="TEST-MARKET",
            event_ticker="TEST-EVENT",
            title="Test Market",
            status=MarketStatus.OPEN,
            yes_bid=45,
            yes_ask=55,
            no_bid=45,
            no_ask=55,
        )

        assert market.ticker == "TEST-MARKET"
        assert market.event_ticker == "TEST-EVENT"
        assert market.status == MarketStatus.OPEN

    def test_market_status_enum(self):
        """Test market status enumeration."""
        assert MarketStatus.OPEN.value == "open"
        assert MarketStatus.CLOSED.value == "closed"
        assert MarketStatus.SETTLED.value == "settled"

    def test_market_optional_fields(self):
        """Test optional fields default correctly."""
        market = Market(
            ticker="TEST",
            event_ticker="EVENT",
            title="Test",
            status="open",
            yes_bid=50,
            yes_ask=50,
            no_bid=50,
            no_ask=50,
        )

        assert market.subtitle is None
        assert market.last_price is None
        assert market.volume == 0


class TestOrder:
    """Tests for Order model."""

    def test_order_creation(self):
        """Test basic order creation."""
        order = Order(
            order_id="order-123",
            ticker="TEST-MARKET",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            type=OrderType.LIMIT,
            status=OrderStatus.RESTING,
            yes_price=50,
            no_price=50,
            count=10,
            remaining_count=10,
            created_time=datetime.now(),
        )

        assert order.order_id == "order-123"
        assert order.side == OrderSide.YES
        assert order.action == OrderAction.BUY

    def test_order_enums(self):
        """Test order enumeration values."""
        assert OrderSide.YES.value == "yes"
        assert OrderSide.NO.value == "no"
        assert OrderAction.BUY.value == "buy"
        assert OrderAction.SELL.value == "sell"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.MARKET.value == "market"
        assert OrderStatus.RESTING.value == "resting"
        assert OrderStatus.EXECUTED.value == "executed"


class TestPosition:
    """Tests for Position model."""

    def test_position_creation(self):
        """Test basic position creation."""
        position = Position(
            ticker="TEST-MARKET",
            event_ticker="TEST-EVENT",
            yes_count=10,
            no_count=5,
        )

        assert position.ticker == "TEST-MARKET"
        assert position.yes_count == 10
        assert position.no_count == 5

    def test_position_net_position_long_yes(self):
        """Test net position calculation for long yes."""
        position = Position(
            ticker="TEST",
            event_ticker="EVENT",
            yes_count=10,
            no_count=0,
        )

        assert position.net_position == 10

    def test_position_net_position_long_no(self):
        """Test net position calculation for long no."""
        position = Position(
            ticker="TEST",
            event_ticker="EVENT",
            yes_count=0,
            no_count=10,
        )

        assert position.net_position == -10

    def test_position_net_position_mixed(self):
        """Test net position calculation for mixed."""
        position = Position(
            ticker="TEST",
            event_ticker="EVENT",
            yes_count=15,
            no_count=5,
        )

        assert position.net_position == 10


class TestOrderBook:
    """Tests for OrderBook model."""

    def test_orderbook_creation(self):
        """Test basic orderbook creation."""
        orderbook = OrderBook(
            ticker="TEST-MARKET",
            yes_bids=[OrderBookLevel(price=45, count=100)],
            yes_asks=[OrderBookLevel(price=55, count=100)],
        )

        assert orderbook.ticker == "TEST-MARKET"
        assert len(orderbook.yes_bids) == 1
        assert len(orderbook.yes_asks) == 1

    def test_orderbook_best_prices(self):
        """Test best price properties."""
        orderbook = OrderBook(
            ticker="TEST",
            yes_bids=[
                OrderBookLevel(price=45, count=100),
                OrderBookLevel(price=44, count=50),
            ],
            yes_asks=[
                OrderBookLevel(price=55, count=100),
                OrderBookLevel(price=56, count=50),
            ],
        )

        assert orderbook.best_yes_bid == 45
        assert orderbook.best_yes_ask == 55

    def test_orderbook_empty_best_prices(self):
        """Test best prices when orderbook is empty."""
        orderbook = OrderBook(ticker="TEST")

        assert orderbook.best_yes_bid is None
        assert orderbook.best_yes_ask is None
        assert orderbook.best_no_bid is None
        assert orderbook.best_no_ask is None

    def test_orderbook_yes_spread(self):
        """Test spread calculation."""
        orderbook = OrderBook(
            ticker="TEST",
            yes_bids=[OrderBookLevel(price=45, count=100)],
            yes_asks=[OrderBookLevel(price=55, count=100)],
        )

        assert orderbook.yes_spread == 10

    def test_orderbook_mid_price(self):
        """Test mid price calculation."""
        orderbook = OrderBook(
            ticker="TEST",
            yes_bids=[OrderBookLevel(price=45, count=100)],
            yes_asks=[OrderBookLevel(price=55, count=100)],
        )

        assert orderbook.mid_price == 50.0

    def test_orderbook_mid_price_empty(self):
        """Test mid price when empty."""
        orderbook = OrderBook(ticker="TEST")
        assert orderbook.mid_price is None


class TestOrderBookLevel:
    """Tests for OrderBookLevel model."""

    def test_level_creation(self):
        """Test basic level creation."""
        level = OrderBookLevel(price=50, count=100)

        assert level.price == 50
        assert level.count == 100
