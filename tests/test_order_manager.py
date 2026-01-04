"""Tests for the OrderManager class."""

import asyncio
import pytest

from src.api import (
    MockRestClient,
    MockWebSocketClient,
    OrderAction,
    OrderSide,
    OrderStatus,
)
from src.execution.order_manager import OrderManager
from src.models import FillResult


@pytest.fixture
def rest_client():
    """Create a mock REST client."""
    return MockRestClient()


@pytest.fixture
def ws_client(rest_client):
    """Create a mock WebSocket client."""
    return MockWebSocketClient(rest_client)


@pytest.fixture
def order_manager(rest_client, ws_client):
    """Create an OrderManager instance."""
    return OrderManager(rest_client, ws_client)


class TestOrderPlacement:
    """Tests for order placement."""

    @pytest.mark.asyncio
    async def test_place_limit_order_success(self, order_manager):
        """Test successful order placement."""
        order = await order_manager.place_limit_order(
            ticker="BTCUSD-24JAN-50000",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=45,
            count=10,
        )

        assert order is not None
        assert order.ticker == "BTCUSD-24JAN-50000"
        assert order.side == OrderSide.YES
        assert order.action == "buy"
        assert order.price == 45
        assert order.count == 10
        assert order.status == "resting"

    @pytest.mark.asyncio
    async def test_place_order_reserves_balance(self, order_manager, rest_client):
        """Test that placing a buy order reserves balance."""
        initial_balance = (await rest_client.get_balance()).available_balance

        await order_manager.place_limit_order(
            ticker="BTCUSD-24JAN-50000",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=20,
        )

        new_balance = (await rest_client.get_balance()).available_balance
        assert new_balance == initial_balance - (50 * 20)

    @pytest.mark.asyncio
    async def test_place_multiple_orders(self, order_manager):
        """Test placing multiple orders."""
        order1 = await order_manager.place_limit_order(
            ticker="MARKET1",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=40,
            count=5,
        )
        order2 = await order_manager.place_limit_order(
            ticker="MARKET2",
            side=OrderSide.NO,
            action=OrderAction.BUY,
            price=60,
            count=10,
        )

        assert order1.order_id != order2.order_id
        assert len(order_manager.get_active_orders()) == 2


class TestOrderCancellation:
    """Tests for order cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, order_manager):
        """Test successful order cancellation."""
        order = await order_manager.place_limit_order(
            ticker="TEST",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        result = await order_manager.cancel_order(order.order_id)
        assert result is True

        managed = order_manager.get_order(order.order_id)
        assert managed.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order(self, order_manager):
        """Test cancelling a non-existent order."""
        result = await order_manager.cancel_order("fake_order_id")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_all_orders(self, order_manager):
        """Test cancelling all orders."""
        # Place multiple orders
        for i in range(3):
            await order_manager.place_limit_order(
                ticker=f"MARKET{i}",
                side=OrderSide.YES,
                action=OrderAction.BUY,
                price=50,
                count=10,
            )

        cancelled = await order_manager.cancel_all_orders()
        assert cancelled == 3
        assert len(order_manager.get_active_orders()) == 0

    @pytest.mark.asyncio
    async def test_cancel_orders_by_ticker(self, order_manager):
        """Test cancelling orders for a specific ticker."""
        await order_manager.place_limit_order(
            ticker="MARKET_A",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )
        await order_manager.place_limit_order(
            ticker="MARKET_B",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        cancelled = await order_manager.cancel_all_orders(ticker="MARKET_A")
        assert cancelled == 1


class TestOrderFills:
    """Tests for order fill handling."""

    @pytest.mark.asyncio
    async def test_wait_for_fill_success(self, order_manager, rest_client, ws_client):
        """Test waiting for order fill."""
        order = await order_manager.place_limit_order(
            ticker="TEST",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        # Simulate fill in background
        async def simulate():
            await asyncio.sleep(0.1)
            await ws_client.simulate_fill_after_delay(order.order_id, delay_seconds=0.1)

        asyncio.create_task(simulate())

        result = await order_manager.wait_for_fill(order.order_id, timeout_seconds=5)
        assert result == FillResult.FILLED

    @pytest.mark.asyncio
    async def test_wait_for_fill_timeout(self, order_manager):
        """Test order fill timeout."""
        order = await order_manager.place_limit_order(
            ticker="TEST",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        # Don't simulate any fill - should timeout
        result = await order_manager.wait_for_fill(order.order_id, timeout_seconds=0.5)
        assert result == FillResult.TIMEOUT

    @pytest.mark.asyncio
    async def test_wait_for_unknown_order(self, order_manager):
        """Test waiting for unknown order."""
        result = await order_manager.wait_for_fill("unknown_order", timeout_seconds=1)
        assert result == FillResult.ERROR


class TestOrderCallbacks:
    """Tests for order update callbacks."""

    @pytest.mark.asyncio
    async def test_order_update_callback(self, order_manager, ws_client):
        """Test that order update callbacks are invoked."""
        updates = []

        def callback(order):
            updates.append(order)

        order_manager.on_order_update(callback)

        order = await order_manager.place_limit_order(
            ticker="TEST",
            side=OrderSide.YES,
            action=OrderAction.BUY,
            price=50,
            count=10,
        )

        # Simulate fill
        await ws_client.simulate_fill_after_delay(order.order_id, delay_seconds=0)
        await asyncio.sleep(0.1)

        assert len(updates) >= 1
