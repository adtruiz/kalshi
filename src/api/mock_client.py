"""Mock Kalshi client for testing purposes."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .client import BaseKalshiClient
from .models import Market, OrderBook, OrderBookLevel


class MockKalshiClient(BaseKalshiClient):
    """
    Mock implementation of Kalshi client for testing.

    Provides configurable mock data for markets and orderbooks.
    """

    def __init__(self) -> None:
        self._markets: Dict[str, Market] = {}
        self._orderbooks: Dict[str, OrderBook] = {}

    def add_market(self, market: Market) -> None:
        """Add a market to the mock data store."""
        self._markets[market.ticker] = market

    def add_orderbook(self, ticker: str, orderbook: OrderBook) -> None:
        """Add an orderbook for a market."""
        self._orderbooks[ticker] = orderbook

    def clear(self) -> None:
        """Clear all mock data."""
        self._markets.clear()
        self._orderbooks.clear()

    async def get_markets(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[List[Market], Optional[str]]:
        """Return mock markets filtered by status and category."""
        markets = list(self._markets.values())

        if status:
            markets = [m for m in markets if m.status == status]

        if category:
            markets = [m for m in markets if m.category == category]

        # Simple pagination simulation
        start = int(cursor) if cursor else 0
        end = start + limit
        page = markets[start:end]

        next_cursor = str(end) if end < len(markets) else None

        return page, next_cursor

    async def get_orderbook(self, ticker: str, depth: int = 10) -> OrderBook:
        """Return mock orderbook for a market."""
        if ticker in self._orderbooks:
            return self._orderbooks[ticker]
        # Return empty orderbook if not configured
        return OrderBook()

    async def get_market(self, ticker: str) -> Market:
        """Return a single mock market."""
        if ticker not in self._markets:
            raise ValueError(f"Market not found: {ticker}")
        return self._markets[ticker]


def create_sample_markets() -> List[Market]:
    """Create sample markets for testing."""
    now = datetime.utcnow()

    return [
        # Good opportunity: wide spread, medium liquidity, upcoming expiration
        Market(
            ticker="KXBTC-24JAN15-T50000",
            title="Will BTC exceed $50,000 on Jan 15?",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
            yes_bid=45,
            yes_ask=52,
            last_price=48,
            category="crypto",
        ),
        # Tight spread - less attractive
        Market(
            ticker="KXETH-24JAN20-T3000",
            title="Will ETH exceed $3,000 on Jan 20?",
            status="active",
            expiration_time=now + timedelta(days=15),
            close_time=now + timedelta(days=15),
            volume_24h=1000,
            liquidity=50000,
            yes_bid=62,
            yes_ask=64,
            last_price=63,
            category="crypto",
        ),
        # Too soon to expire
        Market(
            ticker="KXSPY-24JAN05-T475",
            title="Will SPY close above $475 on Jan 5?",
            status="active",
            expiration_time=now + timedelta(days=1),
            close_time=now + timedelta(days=1),
            volume_24h=2000,
            liquidity=20000,
            yes_bid=70,
            yes_ask=78,
            last_price=74,
            category="finance",
        ),
        # Good opportunity with NO side likely
        Market(
            ticker="KXRAIN-24JAN10-NYC",
            title="Will it rain in NYC on Jan 10?",
            status="active",
            expiration_time=now + timedelta(days=5),
            close_time=now + timedelta(days=5),
            volume_24h=300,
            liquidity=3000,
            yes_bid=25,
            yes_ask=32,
            last_price=28,
            category="weather",
        ),
        # Low volume - should be filtered
        Market(
            ticker="KXLOW-24JAN20-VOL",
            title="Low volume market",
            status="active",
            expiration_time=now + timedelta(days=15),
            close_time=now + timedelta(days=15),
            volume_24h=50,
            liquidity=2000,
            yes_bid=40,
            yes_ask=48,
            last_price=44,
            category="other",
        ),
        # Closed market - should be filtered
        Market(
            ticker="KXCLOSED-24JAN01",
            title="Closed market",
            status="closed",
            expiration_time=now - timedelta(days=2),
            close_time=now - timedelta(days=2),
            volume_24h=0,
            liquidity=0,
            yes_bid=None,
            yes_ask=None,
            category="other",
        ),
        # High liquidity (efficient market) - should be filtered
        Market(
            ticker="KXPOP-24JAN25-HIGH",
            title="Popular high liquidity market",
            status="active",
            expiration_time=now + timedelta(days=20),
            close_time=now + timedelta(days=20),
            volume_24h=10000,
            liquidity=500000,
            yes_bid=55,
            yes_ask=56,
            last_price=55,
            category="politics",
        ),
    ]


def create_sample_orderbook(
    yes_bid: int = 50, yes_ask: int = 55, depth: int = 3
) -> OrderBook:
    """
    Create a sample orderbook with configurable best bid/ask.

    Args:
        yes_bid: Best bid price for YES
        yes_ask: Best ask price for YES
        depth: Number of price levels

    Returns:
        OrderBook with sample data
    """
    yes_bids = []
    yes_asks = []

    # Generate bid levels (decreasing from best)
    for i in range(depth):
        price = yes_bid - i
        if price > 0:
            yes_bids.append(OrderBookLevel(price=price, quantity=100 * (i + 1)))

    # Generate ask levels (increasing from best)
    for i in range(depth):
        price = yes_ask + i
        if price < 100:
            yes_asks.append(OrderBookLevel(price=price, quantity=100 * (i + 1)))

    return OrderBook(yes_bids=yes_bids, yes_asks=yes_asks)
