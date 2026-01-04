"""Mock interfaces for REST and WebSocket clients.

These mock implementations simulate the Kalshi API behavior for testing purposes.
The real implementations will be built in a separate worktree.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4


class OrderSide(str, Enum):
    """Order side (yes/no)."""
    YES = "yes"
    NO = "no"


class OrderAction(str, Enum):
    """Order action (buy/sell)."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order status."""
    RESTING = "resting"
    PENDING = "pending"
    EXECUTED = "executed"
    CANCELED = "canceled"


@dataclass
class Order:
    """Represents a Kalshi order."""
    order_id: str
    ticker: str
    side: OrderSide
    action: OrderAction
    price: int  # in cents
    count: int
    filled_count: int = 0
    remaining_count: int = 0
    status: OrderStatus = OrderStatus.RESTING
    created_time: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        self.remaining_count = self.count - self.filled_count


@dataclass
class Fill:
    """Represents a fill event."""
    trade_id: str
    order_id: str
    ticker: str
    side: OrderSide
    action: OrderAction
    price: int
    count: int
    created_time: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    """Represents a market position from the API."""
    ticker: str
    market_exposure: int  # net contracts (positive = yes, negative = no)
    realized_pnl: int  # in cents
    resting_order_count: int


@dataclass
class Balance:
    """Account balance information."""
    balance: int  # in cents
    available_balance: int  # in cents (balance - reserved for orders)
    bonus_balance: int = 0


class MockRestClient:
    """Mock REST client simulating Kalshi API responses."""

    def __init__(self):
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._balance = Balance(balance=100000, available_balance=100000)  # $1000
        self._fill_probability: float = 0.8
        self._fill_delay_seconds: float = 2.0

    async def get_balance(self) -> Balance:
        """Get account balance."""
        return self._balance

    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        return list(self._positions.values())

    async def get_position(self, ticker: str) -> Optional[Position]:
        """Get position for a specific ticker."""
        return self._positions.get(ticker)

    async def create_order(
        self,
        ticker: str,
        side: OrderSide,
        action: OrderAction,
        price: int,
        count: int,
    ) -> Order:
        """Create a new limit order."""
        order_id = f"order_{uuid4().hex[:12]}"
        order = Order(
            order_id=order_id,
            ticker=ticker,
            side=side,
            action=action,
            price=price,
            count=count,
        )
        self._orders[order_id] = order

        # Reserve balance for buy orders
        if action == OrderAction.BUY:
            cost = price * count
            self._balance.available_balance -= cost

        return order

    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self._orders.get(order_id)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        order = self._orders.get(order_id)
        if not order:
            return False

        if order.status in (OrderStatus.EXECUTED, OrderStatus.CANCELED):
            return False

        order.status = OrderStatus.CANCELED

        # Release reserved balance
        if order.action == OrderAction.BUY:
            refund = order.price * order.remaining_count
            self._balance.available_balance += refund

        return True

    async def get_orders(
        self,
        ticker: Optional[str] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Order]:
        """Get orders with optional filtering."""
        orders = list(self._orders.values())

        if ticker:
            orders = [o for o in orders if o.ticker == ticker]
        if status:
            orders = [o for o in orders if o.status == status]

        return orders

    def set_fill_probability(self, probability: float):
        """Set the probability that orders will fill (for testing)."""
        self._fill_probability = probability

    def set_balance(self, balance: int, available: Optional[int] = None):
        """Set the account balance (for testing)."""
        self._balance.balance = balance
        self._balance.available_balance = available if available is not None else balance

    def simulate_fill(self, order_id: str, fill_count: Optional[int] = None):
        """Simulate a fill event for an order (for testing)."""
        order = self._orders.get(order_id)
        if not order or order.status != OrderStatus.RESTING:
            return None

        count_to_fill = fill_count if fill_count else order.remaining_count
        count_to_fill = min(count_to_fill, order.remaining_count)

        order.filled_count += count_to_fill
        order.remaining_count -= count_to_fill

        if order.remaining_count == 0:
            order.status = OrderStatus.EXECUTED

        # Update position
        ticker = order.ticker
        if ticker not in self._positions:
            self._positions[ticker] = Position(
                ticker=ticker,
                market_exposure=0,
                realized_pnl=0,
                resting_order_count=0,
            )

        pos = self._positions[ticker]
        if order.action == OrderAction.BUY:
            if order.side == OrderSide.YES:
                pos.market_exposure += count_to_fill
            else:
                pos.market_exposure -= count_to_fill
        else:  # SELL
            if order.side == OrderSide.YES:
                pos.market_exposure -= count_to_fill
            else:
                pos.market_exposure += count_to_fill

        return Fill(
            trade_id=f"fill_{uuid4().hex[:12]}",
            order_id=order_id,
            ticker=order.ticker,
            side=order.side,
            action=order.action,
            price=order.price,
            count=count_to_fill,
        )


class MockWebSocketClient:
    """Mock WebSocket client for order updates."""

    def __init__(self, rest_client: MockRestClient):
        self._rest_client = rest_client
        self._order_callbacks: List[Callable[[Order], None]] = []
        self._fill_callbacks: List[Callable[[Fill], None]] = []
        self._connected = False
        self._fill_task: Optional[asyncio.Task] = None

    async def connect(self):
        """Connect to WebSocket."""
        self._connected = True

    async def disconnect(self):
        """Disconnect from WebSocket."""
        self._connected = False
        if self._fill_task:
            self._fill_task.cancel()
            self._fill_task = None

    def on_order_update(self, callback: Callable[[Order], None]):
        """Register callback for order updates."""
        self._order_callbacks.append(callback)

    def on_fill(self, callback: Callable[[Fill], None]):
        """Register callback for fill events."""
        self._fill_callbacks.append(callback)

    async def subscribe_orders(self):
        """Subscribe to order updates."""
        pass

    def _notify_order_update(self, order: Order):
        """Notify all order callbacks."""
        for callback in self._order_callbacks:
            callback(order)

    def _notify_fill(self, fill: Fill):
        """Notify all fill callbacks."""
        for callback in self._fill_callbacks:
            callback(fill)

    async def simulate_fill_after_delay(
        self,
        order_id: str,
        delay_seconds: float = 2.0,
        fill_count: Optional[int] = None,
    ):
        """Simulate a fill event after a delay (for testing)."""
        await asyncio.sleep(delay_seconds)
        fill = self._rest_client.simulate_fill(order_id, fill_count)
        if fill:
            order = await self._rest_client.get_order(order_id)
            self._notify_fill(fill)
            if order:
                self._notify_order_update(order)


@dataclass
class SpreadOpportunity:
    """Represents a detected spread trading opportunity."""
    ticker: str
    side: OrderSide
    bid_price: int  # cents
    ask_price: int  # cents
    spread_cents: int
    volume_24h: int
    liquidity: int
    days_to_expiration: int
    detected_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def expected_profit_cents(self) -> int:
        """Expected profit in cents per contract."""
        return self.spread_cents - 2  # Account for fees (1 cent each side)
