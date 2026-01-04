"""Position tracking models for the execution engine."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.api.mock_clients import OrderSide


class PositionStatus(str, Enum):
    """Status of a tracked position."""
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class TrackedPosition:
    """
    Represents a tracked position in the portfolio.

    This is the internal representation used by the position tracker,
    as opposed to the raw Position data from the API.
    """
    ticker: str
    side: OrderSide
    quantity: int
    avg_entry_price: int  # in cents
    current_price: int = 0  # in cents
    unrealized_pnl: int = 0  # in cents
    realized_pnl: int = 0  # in cents
    entry_time: datetime = field(default_factory=datetime.utcnow)
    status: PositionStatus = PositionStatus.OPEN
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self._calculate_pnl()

    def _calculate_pnl(self):
        """Calculate unrealized PnL based on current price."""
        if self.current_price > 0:
            if self.side == OrderSide.YES:
                # Long YES: profit when current > entry
                self.unrealized_pnl = (self.current_price - self.avg_entry_price) * self.quantity
            else:
                # Long NO: profit when current < entry (or inverse)
                self.unrealized_pnl = (self.avg_entry_price - self.current_price) * self.quantity

    def update_price(self, new_price: int):
        """Update current price and recalculate PnL."""
        self.current_price = new_price
        self.last_updated = datetime.utcnow()
        self._calculate_pnl()

    def add_to_position(self, qty: int, price: int):
        """Add contracts to the position."""
        total_cost = (self.avg_entry_price * self.quantity) + (price * qty)
        self.quantity += qty
        self.avg_entry_price = total_cost // self.quantity if self.quantity > 0 else 0
        self.last_updated = datetime.utcnow()
        self._calculate_pnl()

    def reduce_position(self, qty: int, price: int) -> int:
        """
        Reduce position and calculate realized PnL.

        Returns the realized PnL from this reduction.
        """
        qty = min(qty, self.quantity)
        if qty == 0:
            return 0

        # Calculate realized PnL for this portion
        if self.side == OrderSide.YES:
            pnl = (price - self.avg_entry_price) * qty
        else:
            pnl = (self.avg_entry_price - price) * qty

        self.realized_pnl += pnl
        self.quantity -= qty
        self.last_updated = datetime.utcnow()

        if self.quantity == 0:
            self.status = PositionStatus.CLOSED

        self._calculate_pnl()
        return pnl

    @property
    def total_pnl(self) -> int:
        """Total PnL (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def cost_basis(self) -> int:
        """Total cost basis of the position in cents."""
        return self.avg_entry_price * self.quantity

    @property
    def current_value(self) -> int:
        """Current value of the position in cents."""
        return self.current_price * self.quantity

    @property
    def pnl_percent(self) -> float:
        """PnL as a percentage of cost basis."""
        if self.cost_basis == 0:
            return 0.0
        return (self.total_pnl / self.cost_basis) * 100


@dataclass
class ManagedOrder:
    """
    Represents an order being managed by the OrderManager.

    Wraps the API Order with additional tracking info.
    """
    order_id: str
    ticker: str
    side: OrderSide
    action: str  # 'buy' or 'sell'
    price: int
    count: int
    filled_count: int = 0
    remaining_count: int = 0
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.remaining_count == 0:
            self.remaining_count = self.count - self.filled_count


class FillResult(str, Enum):
    """Result of waiting for an order fill."""
    FILLED = "filled"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class TradeResult:
    """Result of executing a spread trade."""
    success: bool
    ticker: str
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    buy_fill_result: Optional[FillResult] = None
    sell_fill_result: Optional[FillResult] = None
    quantity_filled: int = 0
    entry_price: int = 0
    exit_price: int = 0
    gross_pnl: int = 0  # in cents
    fees: int = 0  # in cents
    net_pnl: int = 0  # in cents
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
