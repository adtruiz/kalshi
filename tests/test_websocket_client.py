"""Tests for WebSocket client."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.api.websocket_client import (
    ChannelType,
    KalshiWebSocketClient,
    MessageType,
)


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
    settings.ws_url = "wss://demo-api.kalshi.co/trade-api/ws/v2"
    return settings


class TestKalshiWebSocketClient:
    """Tests for KalshiWebSocketClient class."""

    def test_init(self, mock_settings):
        """Test client initialization."""
        client = KalshiWebSocketClient(settings=mock_settings)
        assert client._ws_url == "wss://demo-api.kalshi.co/trade-api/ws/v2"
        assert client._websocket is None
        assert client._running is False

    def test_register_callback(self, mock_settings):
        """Test callback registration."""
        client = KalshiWebSocketClient(settings=mock_settings)
        callback = MagicMock()

        client.register_callback(MessageType.ORDERBOOK_DELTA, callback)

        assert MessageType.ORDERBOOK_DELTA.value in client._callbacks
        assert callback in client._callbacks[MessageType.ORDERBOOK_DELTA.value]

    def test_unregister_callback(self, mock_settings):
        """Test callback unregistration."""
        client = KalshiWebSocketClient(settings=mock_settings)
        callback = MagicMock()

        client.register_callback(MessageType.ORDERBOOK_DELTA, callback)
        client.unregister_callback(MessageType.ORDERBOOK_DELTA, callback)

        assert callback not in client._callbacks.get(MessageType.ORDERBOOK_DELTA.value, [])

    def test_dispatch_message(self, mock_settings):
        """Test message dispatching to callbacks."""
        client = KalshiWebSocketClient(settings=mock_settings)
        callback = MagicMock()
        client.register_callback(MessageType.ORDERBOOK_DELTA, callback)

        message = {"type": "orderbook_delta", "ticker": "TEST", "data": {}}
        client._dispatch_message(message)

        callback.assert_called_once_with(message)

    def test_dispatch_message_no_callbacks(self, mock_settings):
        """Test dispatching with no registered callbacks."""
        client = KalshiWebSocketClient(settings=mock_settings)

        # Should not raise
        message = {"type": "orderbook_delta", "ticker": "TEST"}
        client._dispatch_message(message)

    def test_dispatch_message_callback_error(self, mock_settings):
        """Test that callback errors don't break dispatch."""
        client = KalshiWebSocketClient(settings=mock_settings)

        error_callback = MagicMock(side_effect=Exception("Callback error"))
        success_callback = MagicMock()

        client.register_callback(MessageType.ORDERBOOK_DELTA, error_callback)
        client.register_callback(MessageType.ORDERBOOK_DELTA, success_callback)

        message = {"type": "orderbook_delta", "ticker": "TEST"}
        client._dispatch_message(message)

        # Both callbacks should be called despite error
        error_callback.assert_called_once()
        success_callback.assert_called_once()

    def test_next_cmd_id(self, mock_settings):
        """Test command ID generation."""
        client = KalshiWebSocketClient(settings=mock_settings)

        id1 = client._next_cmd_id()
        id2 = client._next_cmd_id()
        id3 = client._next_cmd_id()

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    @pytest.mark.asyncio
    async def test_connect(self, mock_settings):
        """Test WebSocket connection."""
        with patch("src.api.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_connect.return_value = mock_ws

            client = KalshiWebSocketClient(settings=mock_settings)
            await client.connect()

            assert client._websocket is mock_ws
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_settings):
        """Test WebSocket disconnection."""
        with patch("src.api.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_connect.return_value = mock_ws

            client = KalshiWebSocketClient(settings=mock_settings)
            await client.connect()
            await client.disconnect()

            mock_ws.close.assert_called_once()
            assert client._websocket is None

    @pytest.mark.asyncio
    async def test_subscribe(self, mock_settings):
        """Test channel subscription."""
        with patch("src.api.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_connect.return_value = mock_ws

            client = KalshiWebSocketClient(settings=mock_settings)
            await client.connect()
            await client.subscribe(ChannelType.ORDERBOOK, ["TICKER1", "TICKER2"])

            # Verify subscription was tracked
            assert "orderbook" in client._subscriptions
            assert "TICKER1" in client._subscriptions["orderbook"]
            assert "TICKER2" in client._subscriptions["orderbook"]

            # Verify message was sent
            mock_ws.send.assert_called_once()
            sent_msg = json.loads(mock_ws.send.call_args[0][0])
            assert sent_msg["cmd"] == "subscribe"
            assert sent_msg["params"]["channels"] == ["orderbook"]
            assert set(sent_msg["params"]["market_tickers"]) == {"TICKER1", "TICKER2"}

    @pytest.mark.asyncio
    async def test_unsubscribe(self, mock_settings):
        """Test channel unsubscription."""
        with patch("src.api.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_connect.return_value = mock_ws

            client = KalshiWebSocketClient(settings=mock_settings)
            await client.connect()

            # First subscribe
            await client.subscribe(ChannelType.ORDERBOOK, ["TICKER1", "TICKER2"])

            # Then unsubscribe
            await client.unsubscribe(ChannelType.ORDERBOOK, ["TICKER1"])

            # Verify TICKER1 was removed from subscriptions
            assert "TICKER1" not in client._subscriptions["orderbook"]
            assert "TICKER2" in client._subscriptions["orderbook"]

    @pytest.mark.asyncio
    async def test_send_not_connected(self, mock_settings):
        """Test sending when not connected raises error."""
        client = KalshiWebSocketClient(settings=mock_settings)

        with pytest.raises(ConnectionError):
            await client._send({"test": "message"})

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_settings):
        """Test async context manager."""
        with patch("src.api.websocket_client.websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_ws = AsyncMock()
            mock_ws.closed = False
            mock_ws.recv = AsyncMock(side_effect=asyncio.CancelledError)
            mock_connect.return_value = mock_ws

            async with KalshiWebSocketClient(settings=mock_settings) as client:
                assert client._running is True

            assert client._running is False


class TestChannelType:
    """Tests for ChannelType enum."""

    def test_channel_values(self):
        """Test channel type values."""
        assert ChannelType.ORDERBOOK.value == "orderbook"
        assert ChannelType.TICKER.value == "ticker"
        assert ChannelType.TRADE.value == "trade"
        assert ChannelType.FILL.value == "fill"


class TestMessageType:
    """Tests for MessageType enum."""

    def test_message_type_values(self):
        """Test message type values."""
        assert MessageType.ORDERBOOK_SNAPSHOT.value == "orderbook_snapshot"
        assert MessageType.ORDERBOOK_DELTA.value == "orderbook_delta"
        assert MessageType.TRADE.value == "trade"
        assert MessageType.TICKER.value == "ticker"
        assert MessageType.FILL.value == "fill"
        assert MessageType.ORDER_UPDATE.value == "order_update"
