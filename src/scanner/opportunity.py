"""Spread opportunity data model for arbitrage detection."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SpreadOpportunity:
    """
    Represents a detected spread arbitrage opportunity in a Kalshi market.

    Attributes:
        ticker: The market ticker symbol (e.g., 'KXBTC-24JAN01-T50000')
        market_title: Human-readable market title
        yes_bid: Best bid price for YES contracts in cents (0-100)
        yes_ask: Best ask price for YES contracts in cents (0-100)
        spread_cents: The bid-ask spread in cents (yes_ask - yes_bid)
        spread_pct: The spread as a percentage of the midpoint
        likely_side: Which side is more likely to win ('yes' or 'no')
        probability: Estimated probability of the likely side (0-1)
        volume_24h: 24-hour trading volume in contracts
        liquidity: Market liquidity score/value
        expiration: Market expiration datetime
        expected_profit: Expected profit per contract in cents
        score: Composite ranking score for opportunity prioritization
    """

    ticker: str
    market_title: str
    yes_bid: int
    yes_ask: int
    spread_cents: int
    spread_pct: float
    likely_side: str
    probability: float
    volume_24h: int
    liquidity: int
    expiration: datetime
    expected_profit: float = field(default=0.0)
    score: float = field(default=0.0)

    def __post_init__(self) -> None:
        """Validate opportunity data after initialization."""
        if self.yes_bid < 0 or self.yes_bid > 100:
            raise ValueError(f"yes_bid must be 0-100, got {self.yes_bid}")
        if self.yes_ask < 0 or self.yes_ask > 100:
            raise ValueError(f"yes_ask must be 0-100, got {self.yes_ask}")
        if self.yes_bid > self.yes_ask:
            raise ValueError(
                f"yes_bid ({self.yes_bid}) cannot exceed yes_ask ({self.yes_ask})"
            )
        if self.likely_side not in ("yes", "no"):
            raise ValueError(f"likely_side must be 'yes' or 'no', got {self.likely_side}")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError(f"probability must be 0-1, got {self.probability}")

    @property
    def midpoint(self) -> float:
        """Calculate the midpoint price in cents."""
        return (self.yes_bid + self.yes_ask) / 2.0

    @property
    def no_bid(self) -> int:
        """Calculate implied NO bid price (100 - yes_ask)."""
        return 100 - self.yes_ask

    @property
    def no_ask(self) -> int:
        """Calculate implied NO ask price (100 - yes_bid)."""
        return 100 - self.yes_bid

    def to_dict(self) -> dict:
        """Convert opportunity to dictionary format."""
        return {
            "ticker": self.ticker,
            "market_title": self.market_title,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "spread_cents": self.spread_cents,
            "spread_pct": self.spread_pct,
            "likely_side": self.likely_side,
            "probability": self.probability,
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "expiration": self.expiration.isoformat(),
            "expected_profit": self.expected_profit,
            "score": self.score,
        }

    def __repr__(self) -> str:
        return (
            f"SpreadOpportunity({self.ticker}, "
            f"spread={self.spread_cents}c, "
            f"side={self.likely_side}, "
            f"prob={self.probability:.1%}, "
            f"score={self.score:.2f})"
        )
