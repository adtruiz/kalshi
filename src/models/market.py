"""Market data models for Kalshi API."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MarketStatus(str, Enum):
    """Market status enumeration."""
    OPEN = "open"
    CLOSED = "closed"
    SETTLED = "settled"


class Market(BaseModel):
    """Represents a Kalshi market."""

    ticker: str = Field(..., description="Unique market ticker")
    event_ticker: str = Field(..., description="Parent event ticker")
    title: str = Field(..., description="Market title")
    subtitle: Optional[str] = Field(None, description="Market subtitle")
    status: MarketStatus = Field(..., description="Current market status")
    yes_bid: int = Field(..., description="Best yes bid price in cents")
    yes_ask: int = Field(..., description="Best yes ask price in cents")
    no_bid: int = Field(..., description="Best no bid price in cents")
    no_ask: int = Field(..., description="Best no ask price in cents")
    last_price: Optional[int] = Field(None, description="Last trade price in cents")
    volume: int = Field(default=0, description="Total volume traded")
    volume_24h: int = Field(default=0, description="24h volume traded")
    open_interest: int = Field(default=0, description="Open interest")
    close_time: Optional[datetime] = Field(None, description="Market close time")
    expiration_time: Optional[datetime] = Field(None, description="Market expiration time")

    model_config = ConfigDict(use_enum_values=True)


class MarketResponse(BaseModel):
    """Response wrapper for single market."""

    market: Market


class MarketsResponse(BaseModel):
    """Response wrapper for multiple markets."""

    markets: list[Market]
    cursor: Optional[str] = Field(None, description="Pagination cursor")
