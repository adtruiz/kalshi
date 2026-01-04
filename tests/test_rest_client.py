"""Tests for REST client."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponseError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.api.rest_client import KalshiAPIError, KalshiRestClient
from src.models import Market, MarketStatus, Order, OrderBook, Position


@pytest.fixture
def test_private_key():
    """Generate a test RSA private key."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


@pytest.fixture
def test_key_path(test_private_key):
    """Create a temporary PEM file with the test key."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as f:
        f.write(
            test_private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return Path(f.name)


@pytest.fixture
def mock_settings(test_key_path):
    """Create mock settings."""
    settings = MagicMock()
    settings.kalshi_api_key = "test-api-key"
    settings.private_key_path = test_key_path
    settings.read_rate_limit = 20
    settings.write_rate_limit = 10
    settings.base_url = "https://demo-api.kalshi.co/trade-api/v2"
    return settings


@pytest.fixture
def mock_session():
    """Create mock aiohttp session."""
    session = MagicMock()
    session.closed = False
    return session


class TestKalshiRestClient:
    """Tests for KalshiRestClient class."""

    def test_init(self, mock_settings, mock_session):
        """Test client initialization."""
        client = KalshiRestClient(settings=mock_settings, session=mock_session)
        assert client._base_url == "https://demo-api.kalshi.co/trade-api/v2"

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_settings):
        """Test async context manager."""
        async with KalshiRestClient(settings=mock_settings) as client:
            assert client._session is not None
        assert client._session.closed

    @pytest.mark.asyncio
    async def test_get_markets(self, mock_settings):
        """Test get_markets endpoint."""
        mock_response = {
            "markets": [
                {
                    "ticker": "TEST-MARKET",
                    "event_ticker": "TEST-EVENT",
                    "title": "Test Market",
                    "status": "open",
                    "yes_bid": 45,
                    "yes_ask": 55,
                    "no_bid": 45,
                    "no_ask": 55,
                }
            ],
            "cursor": "next-page",
        }

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            markets, cursor = await client.get_markets(status="open", limit=10)

            assert len(markets) == 1
            assert markets[0].ticker == "TEST-MARKET"
            assert markets[0].status == MarketStatus.OPEN
            assert cursor == "next-page"

    @pytest.mark.asyncio
    async def test_get_market(self, mock_settings):
        """Test get_market endpoint."""
        mock_response = {
            "market": {
                "ticker": "TEST-MARKET",
                "event_ticker": "TEST-EVENT",
                "title": "Test Market",
                "status": "open",
                "yes_bid": 45,
                "yes_ask": 55,
                "no_bid": 45,
                "no_ask": 55,
            }
        }

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            market = await client.get_market("TEST-MARKET")

            assert market.ticker == "TEST-MARKET"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_orderbook(self, mock_settings):
        """Test get_orderbook endpoint."""
        mock_response = {
            "orderbook": {
                "yes": [[[45, 100], [44, 50]], [[55, 100], [56, 50]]],
                "no": [[[45, 100]], [[55, 100]]],
            }
        }

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            orderbook = await client.get_orderbook("TEST-MARKET")

            assert orderbook.ticker == "TEST-MARKET"
            assert isinstance(orderbook, OrderBook)

    @pytest.mark.asyncio
    async def test_create_order(self, mock_settings):
        """Test create_order endpoint."""
        mock_response = {
            "order": {
                "order_id": "order-123",
                "ticker": "TEST-MARKET",
                "side": "yes",
                "action": "buy",
                "type": "limit",
                "status": "resting",
                "yes_price": 50,
                "no_price": 50,
                "count": 10,
                "remaining_count": 10,
                "created_time": "2024-01-01T00:00:00Z",
            }
        }

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            order = await client.create_order(
                ticker="TEST-MARKET",
                side="yes",
                action="buy",
                count=10,
                price=50,
            )

            assert order.order_id == "order-123"
            assert order.ticker == "TEST-MARKET"

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, mock_settings):
        """Test cancel_order success."""
        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {}

            client = KalshiRestClient(settings=mock_settings)
            result = await client.cancel_order("order-123")

            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_order_not_found(self, mock_settings):
        """Test cancel_order when order not found."""
        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = KalshiAPIError(404, "Order not found")

            client = KalshiRestClient(settings=mock_settings)
            result = await client.cancel_order("nonexistent-order")

            assert result is False

    @pytest.mark.asyncio
    async def test_get_orders(self, mock_settings):
        """Test get_orders endpoint."""
        mock_response = {
            "orders": [
                {
                    "order_id": "order-123",
                    "ticker": "TEST-MARKET",
                    "side": "yes",
                    "action": "buy",
                    "type": "limit",
                    "status": "resting",
                    "yes_price": 50,
                    "no_price": 50,
                    "count": 10,
                    "remaining_count": 10,
                    "created_time": "2024-01-01T00:00:00Z",
                }
            ],
            "cursor": None,
        }

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            orders, cursor = await client.get_orders(status="resting")

            assert len(orders) == 1
            assert orders[0].order_id == "order-123"

    @pytest.mark.asyncio
    async def test_get_balance(self, mock_settings):
        """Test get_balance endpoint."""
        mock_response = {"balance": 10000}  # 100.00 dollars

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            balance = await client.get_balance()

            assert balance == 100.0

    @pytest.mark.asyncio
    async def test_get_positions(self, mock_settings):
        """Test get_positions endpoint."""
        mock_response = {
            "market_positions": [
                {
                    "ticker": "TEST-MARKET",
                    "event_ticker": "TEST-EVENT",
                    "yes_count": 10,
                    "no_count": 0,
                    "market_exposure": 500,
                    "realized_pnl": 0,
                }
            ],
            "cursor": None,
        }

        with patch.object(KalshiRestClient, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            client = KalshiRestClient(settings=mock_settings)
            positions, cursor = await client.get_positions()

            assert len(positions) == 1
            assert positions[0].ticker == "TEST-MARKET"
            assert positions[0].yes_count == 10


class TestKalshiAPIError:
    """Tests for KalshiAPIError."""

    def test_error_message(self):
        """Test error message formatting."""
        error = KalshiAPIError(400, "Bad request", "INVALID_PARAM")
        assert str(error) == "[400] INVALID_PARAM: Bad request"

    def test_error_without_code(self):
        """Test error message without code."""
        error = KalshiAPIError(500, "Internal error")
        assert str(error) == "[500] ERROR: Internal error"

    def test_error_attributes(self):
        """Test error attributes."""
        error = KalshiAPIError(404, "Not found", "NOT_FOUND")
        assert error.status == 404
        assert error.message == "Not found"
        assert error.code == "NOT_FOUND"
