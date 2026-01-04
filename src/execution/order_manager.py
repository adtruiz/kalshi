"""Order management for the execution engine."""

import asyncio
from datetime import datetime
from typing import Callable, Dict, List, Optional

from src.api import (
    Fill,
    MockRestClient,
    MockWebSocketClient,
    Order,
    OrderAction,
    OrderSide,
    OrderStatus,
)
from src.models import FillResult, ManagedOrder
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.order_manager")


class OrderManager:
    """
    Manages order lifecycle for the execution engine.

    Handles order placement, cancellation, and fill tracking
    through both REST API and WebSocket updates.
    """

    def __init__(
        self,
        rest_client: MockRestClient,
        ws_client: MockWebSocketClient,
    ):
        self._rest_client = rest_client
        self._ws_client = ws_client
        self._orders: Dict[str, ManagedOrder] = {}
        self._fill_events: Dict[str, asyncio.Event] = {}
        self._order_callbacks: List[Callable[[ManagedOrder], None]] = []

        # Register for WebSocket updates
        self._ws_client.on_order_update(self._handle_order_update)
        self._ws_client.on_fill(self._handle_fill)

    def _handle_order_update(self, order: Order):
        """Handle order update from WebSocket."""
        if order.order_id in self._orders:
            managed = self._orders[order.order_id]
            managed.filled_count = order.filled_count
            managed.remaining_count = order.remaining_count
            managed.status = order.status.value

            logger.debug(
                f"Order update: {order.order_id} status={order.status.value} "
                f"filled={order.filled_count}/{order.count}"
            )

            # Notify callbacks
            for callback in self._order_callbacks:
                try:
                    callback(managed)
                except Exception as e:
                    logger.error(f"Error in order callback: {e}")

            # Signal fill event if order is complete
            if order.status in (OrderStatus.EXECUTED, OrderStatus.CANCELED):
                if order.order_id in self._fill_events:
                    self._fill_events[order.order_id].set()

    def _handle_fill(self, fill: Fill):
        """Handle fill event from WebSocket."""
        logger.info(
            f"Fill received: order={fill.order_id} ticker={fill.ticker} "
            f"price={fill.price} count={fill.count}"
        )

        if fill.order_id in self._orders:
            managed = self._orders[fill.order_id]
            managed.filled_count += fill.count
            managed.remaining_count -= fill.count

            if managed.remaining_count <= 0:
                managed.status = "executed"
                if fill.order_id in self._fill_events:
                    self._fill_events[fill.order_id].set()

    async def place_limit_order(
        self,
        ticker: str,
        side: OrderSide,
        action: OrderAction,
        price: int,
        count: int,
    ) -> ManagedOrder:
        """
        Place a limit order.

        Args:
            ticker: Market ticker
            side: YES or NO
            action: BUY or SELL
            price: Price in cents
            count: Number of contracts

        Returns:
            ManagedOrder tracking the order
        """
        logger.info(
            f"Placing order: {action.value} {count} {side.value} @ {price}c on {ticker}"
        )

        try:
            order = await self._rest_client.create_order(
                ticker=ticker,
                side=side,
                action=action,
                price=price,
                count=count,
            )

            managed = ManagedOrder(
                order_id=order.order_id,
                ticker=ticker,
                side=side,
                action=action.value,
                price=price,
                count=count,
                filled_count=0,
                remaining_count=count,
                status="resting",
            )

            self._orders[order.order_id] = managed
            self._fill_events[order.order_id] = asyncio.Event()

            logger.info(f"Order placed: {order.order_id}")
            return managed

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: The order ID to cancel

        Returns:
            True if cancelled successfully
        """
        logger.info(f"Cancelling order: {order_id}")

        try:
            result = await self._rest_client.cancel_order(order_id)

            if result and order_id in self._orders:
                self._orders[order_id].status = "cancelled"
                if order_id in self._fill_events:
                    self._fill_events[order_id].set()

            return result

        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all_orders(self, ticker: Optional[str] = None) -> int:
        """
        Cancel all orders, optionally filtered by ticker.

        Args:
            ticker: Optional ticker to filter by

        Returns:
            Number of orders cancelled
        """
        logger.info(f"Cancelling all orders" + (f" for {ticker}" if ticker else ""))

        orders = await self._rest_client.get_orders(
            ticker=ticker,
            status=OrderStatus.RESTING,
        )

        cancelled = 0
        for order in orders:
            if await self.cancel_order(order.order_id):
                cancelled += 1

        logger.info(f"Cancelled {cancelled} orders")
        return cancelled

    async def wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: float = 300,
    ) -> FillResult:
        """
        Wait for an order to be filled.

        Args:
            order_id: The order ID to wait for
            timeout_seconds: Maximum time to wait (default 5 minutes)

        Returns:
            FillResult indicating the outcome
        """
        if order_id not in self._orders:
            logger.error(f"Unknown order: {order_id}")
            return FillResult.ERROR

        managed = self._orders[order_id]
        fill_event = self._fill_events.get(order_id)

        if not fill_event:
            fill_event = asyncio.Event()
            self._fill_events[order_id] = fill_event

        logger.debug(f"Waiting for fill: {order_id} timeout={timeout_seconds}s")

        try:
            await asyncio.wait_for(fill_event.wait(), timeout=timeout_seconds)

            # Check final state
            order = await self._rest_client.get_order(order_id)
            if not order:
                return FillResult.ERROR

            if order.status == OrderStatus.EXECUTED:
                managed.status = "executed"
                managed.filled_count = order.filled_count
                managed.remaining_count = 0
                logger.info(f"Order filled: {order_id}")
                return FillResult.FILLED

            if order.status == OrderStatus.CANCELED:
                managed.status = "cancelled"
                if order.filled_count > 0:
                    logger.info(f"Order partially filled: {order_id} ({order.filled_count}/{order.count})")
                    return FillResult.PARTIAL
                logger.info(f"Order cancelled: {order_id}")
                return FillResult.CANCELLED

            return FillResult.ERROR

        except asyncio.TimeoutError:
            logger.warning(f"Order timeout: {order_id}")

            # Check for partial fill
            order = await self._rest_client.get_order(order_id)
            if order and order.filled_count > 0:
                managed.filled_count = order.filled_count
                managed.remaining_count = order.remaining_count
                return FillResult.PARTIAL

            return FillResult.TIMEOUT

    def on_order_update(self, callback: Callable[[ManagedOrder], None]):
        """
        Register a callback for order updates.

        Args:
            callback: Function to call on order updates
        """
        self._order_callbacks.append(callback)

    def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        """Get a managed order by ID."""
        return self._orders.get(order_id)

    def get_active_orders(self, ticker: Optional[str] = None) -> List[ManagedOrder]:
        """Get all active (non-completed) orders."""
        orders = [
            o for o in self._orders.values()
            if o.status in ("pending", "resting")
        ]
        if ticker:
            orders = [o for o in orders if o.ticker == ticker]
        return orders
