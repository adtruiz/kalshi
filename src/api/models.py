"""Data models representing Kalshi API responses."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class OrderBookLevel:
    """A single price level in the order book."""

    price: int  # Price in cents (1-99)
    quantity: int  # Number of contracts at this price


@dataclass
class OrderBook:
    """
    Represents the order book for a market.

    YES and NO sides are complementary:
    - YES bid at 60 means someone will pay 60c for YES
    - NO bid at 40 means someone will pay 40c for NO (equivalent to YES ask at 60)
    """

    yes_bids: List[OrderBookLevel] = field(default_factory=list)
    yes_asks: List[OrderBookLevel] = field(default_factory=list)

    @property
    def best_yes_bid(self) -> Optional[int]:
        """Highest price someone is willing to pay for YES."""
        if not self.yes_bids:
            return None
        return max(level.price for level in self.yes_bids)

    @property
    def best_yes_ask(self) -> Optional[int]:
        """Lowest price someone is willing to sell YES."""
        if not self.yes_asks:
            return None
        return min(level.price for level in self.yes_asks)

    @property
    def spread(self) -> Optional[int]:
        """Calculate the bid-ask spread in cents."""
        if self.best_yes_bid is None or self.best_yes_ask is None:
            return None
        return self.best_yes_ask - self.best_yes_bid

    @property
    def midpoint(self) -> Optional[float]:
        """Calculate the midpoint price."""
        if self.best_yes_bid is None or self.best_yes_ask is None:
            return None
        return (self.best_yes_bid + self.best_yes_ask) / 2.0

    @property
    def yes_bid_depth(self) -> int:
        """Total quantity available on the YES bid side."""
        return sum(level.quantity for level in self.yes_bids)

    @property
    def yes_ask_depth(self) -> int:
        """Total quantity available on the YES ask side."""
        return sum(level.quantity for level in self.yes_asks)


@dataclass
class Market:
    """Represents a Kalshi prediction market."""

    ticker: str
    title: str
    status: str  # 'active', 'closed', 'settled'
    expiration_time: datetime
    close_time: datetime
    volume_24h: int
    liquidity: int
    yes_bid: Optional[int] = None  # Best bid for YES in cents
    yes_ask: Optional[int] = None  # Best ask for YES in cents
    last_price: Optional[int] = None
    open_interest: int = 0
    category: str = ""
    event_ticker: str = ""

    @property
    def is_active(self) -> bool:
        """Check if market is currently active for trading."""
        return self.status == "active"

    def days_to_expiration(self, from_time: Optional[datetime] = None) -> float:
        """Calculate days until market expiration."""
        reference = from_time or datetime.utcnow()
        delta = self.expiration_time - reference
        return delta.total_seconds() / 86400  # seconds per day

    def to_dict(self) -> dict:
        """Convert market to dictionary format."""
        return {
            "ticker": self.ticker,
            "title": self.title,
            "status": self.status,
            "expiration_time": self.expiration_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "last_price": self.last_price,
            "open_interest": self.open_interest,
            "category": self.category,
            "event_ticker": self.event_ticker,
        }
