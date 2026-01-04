"""Order data models for Kalshi API."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderSide(str, Enum):
    """Order side enumeration."""
    YES = "yes"
    NO = "no"


class OrderAction(str, Enum):
    """Order action enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enumeration."""
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    RESTING = "resting"
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELED = "canceled"


class Order(BaseModel):
    """Represents a Kalshi order."""

    order_id: str = Field(..., description="Unique order ID")
    ticker: str = Field(..., description="Market ticker")
    side: OrderSide = Field(..., description="Order side (yes/no)")
    action: OrderAction = Field(..., description="Order action (buy/sell)")
    type: OrderType = Field(..., description="Order type (limit/market)")
    status: OrderStatus = Field(..., description="Order status")
    yes_price: int = Field(..., description="Yes price in cents")
    no_price: int = Field(..., description="No price in cents")
    count: int = Field(..., description="Number of contracts")
    remaining_count: int = Field(..., description="Remaining unfilled contracts")
    created_time: datetime = Field(..., description="Order creation time")
    expiration_time: Optional[datetime] = Field(None, description="Order expiration time")

    model_config = ConfigDict(use_enum_values=True)


class CreateOrderRequest(BaseModel):
    """Request model for creating an order."""

    ticker: str = Field(..., description="Market ticker")
    side: OrderSide = Field(..., description="Order side (yes/no)")
    action: OrderAction = Field(..., description="Order action (buy/sell)")
    count: int = Field(..., ge=1, description="Number of contracts")
    type: OrderType = Field(default=OrderType.LIMIT, description="Order type")
    yes_price: Optional[int] = Field(None, ge=1, le=99, description="Yes price in cents (1-99)")
    no_price: Optional[int] = Field(None, ge=1, le=99, description="No price in cents (1-99)")


class OrderResponse(BaseModel):
    """Response wrapper for single order."""

    order: Order


class OrdersResponse(BaseModel):
    """Response wrapper for multiple orders."""

    orders: list[Order]
    cursor: Optional[str] = Field(None, description="Pagination cursor")


class Position(BaseModel):
    """Represents a position in a market."""

    ticker: str = Field(..., description="Market ticker")
    event_ticker: str = Field(..., description="Parent event ticker")
    yes_count: int = Field(default=0, description="Number of yes contracts")
    no_count: int = Field(default=0, description="Number of no contracts")
    market_exposure: int = Field(default=0, description="Market exposure in cents")
    realized_pnl: int = Field(default=0, description="Realized PnL in cents")

    @property
    def net_position(self) -> int:
        """Get net position (positive = long yes, negative = long no)."""
        return self.yes_count - self.no_count


class PositionsResponse(BaseModel):
    """Response wrapper for positions."""

    positions: list[Position]
    cursor: Optional[str] = Field(None, description="Pagination cursor")


class BalanceResponse(BaseModel):
    """Response wrapper for account balance."""

    balance: int = Field(..., description="Account balance in cents")
