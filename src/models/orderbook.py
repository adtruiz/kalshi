"""Orderbook data models for Kalshi API."""

from typing import Optional

from pydantic import BaseModel, Field


class OrderBookLevel(BaseModel):
    """Single price level in the order book."""

    price: int = Field(..., description="Price in cents")
    count: int = Field(..., description="Number of contracts at this level")


class OrderBook(BaseModel):
    """Represents an order book for a market."""

    ticker: str = Field(..., description="Market ticker")
    yes_bids: list[OrderBookLevel] = Field(
        default_factory=list,
        description="Yes side bids (sorted by price descending)"
    )
    yes_asks: list[OrderBookLevel] = Field(
        default_factory=list,
        description="Yes side asks (sorted by price ascending)"
    )
    no_bids: list[OrderBookLevel] = Field(
        default_factory=list,
        description="No side bids (sorted by price descending)"
    )
    no_asks: list[OrderBookLevel] = Field(
        default_factory=list,
        description="No side asks (sorted by price ascending)"
    )

    @property
    def best_yes_bid(self) -> Optional[int]:
        """Get best yes bid price."""
        return self.yes_bids[0].price if self.yes_bids else None

    @property
    def best_yes_ask(self) -> Optional[int]:
        """Get best yes ask price."""
        return self.yes_asks[0].price if self.yes_asks else None

    @property
    def best_no_bid(self) -> Optional[int]:
        """Get best no bid price."""
        return self.no_bids[0].price if self.no_bids else None

    @property
    def best_no_ask(self) -> Optional[int]:
        """Get best no ask price."""
        return self.no_asks[0].price if self.no_asks else None

    @property
    def yes_spread(self) -> Optional[int]:
        """Get yes side spread."""
        if self.best_yes_bid and self.best_yes_ask:
            return self.best_yes_ask - self.best_yes_bid
        return None

    @property
    def no_spread(self) -> Optional[int]:
        """Get no side spread."""
        if self.best_no_bid and self.best_no_ask:
            return self.best_no_ask - self.best_no_bid
        return None

    @property
    def mid_price(self) -> Optional[float]:
        """Get mid price (average of best yes bid and ask)."""
        if self.best_yes_bid and self.best_yes_ask:
            return (self.best_yes_bid + self.best_yes_ask) / 2
        return None


class OrderBookResponse(BaseModel):
    """Response wrapper for order book."""

    orderbook: OrderBook


class OrderBookDelta(BaseModel):
    """Represents a delta update to the order book (from WebSocket)."""

    ticker: str = Field(..., description="Market ticker")
    price: int = Field(..., description="Price level that changed")
    side: str = Field(..., description="Side (yes/no)")
    delta: int = Field(..., description="Change in contracts (positive=added, negative=removed)")
