"""WebSocket client for Kalshi real-time data."""

import asyncio
import json
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from config.settings import Settings, get_settings
from src.auth.kalshi_auth import KalshiAuth
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.websocket")


class MessageType(str, Enum):
    """WebSocket message types."""
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    ORDERBOOK_DELTA = "orderbook_delta"
    TRADE = "trade"
    TICKER = "ticker"
    FILL = "fill"
    ORDER_UPDATE = "order_update"


class ChannelType(str, Enum):
    """WebSocket channel types."""
    ORDERBOOK = "orderbook"
    TICKER = "ticker"
    TRADE = "trade"
    FILL = "fill"


class KalshiWebSocketClient:
    """WebSocket client for Kalshi real-time data streams."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        reconnect_attempts: int = 5,
        reconnect_delay: float = 1.0,
        reconnect_delay_max: float = 60.0,
    ) -> None:
        """
        Initialize WebSocket client.

        Args:
            settings: Application settings
            reconnect_attempts: Max reconnection attempts (0 = infinite)
            reconnect_delay: Initial delay between reconnects
            reconnect_delay_max: Maximum delay between reconnects
        """
        self._settings = settings or get_settings()
        self._auth = KalshiAuth(
            api_key=self._settings.kalshi_api_key,
            private_key_path=self._settings.private_key_path,
        )
        self._ws_url = self._settings.ws_url
        self._reconnect_attempts = reconnect_attempts
        self._reconnect_delay = reconnect_delay
        self._reconnect_delay_max = reconnect_delay_max

        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._subscriptions: Dict[str, Set[str]] = {}  # channel -> set of tickers
        self._callbacks: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._cmd_id = 0

        logger.info(f"WebSocket client initialized for {self._ws_url}")

    def _next_cmd_id(self) -> int:
        """Get next command ID."""
        self._cmd_id += 1
        return self._cmd_id

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if self._websocket and not self._websocket.closed:
            logger.warning("Already connected")
            return

        auth_headers = self._auth.get_ws_auth_headers()
        headers = [(k, v) for k, v in auth_headers.items()]

        logger.info("Connecting to WebSocket...")
        self._websocket = await websockets.connect(
            self._ws_url,
            additional_headers=headers,
            ping_interval=30,
            ping_timeout=10,
        )
        logger.info("WebSocket connected")

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._websocket:
            await self._websocket.close()
            self._websocket = None
            logger.info("WebSocket disconnected")

    async def _send(self, message: Dict[str, Any]) -> None:
        """Send a message over WebSocket."""
        if not self._websocket:
            raise ConnectionError("WebSocket not connected")

        await self._websocket.send(json.dumps(message))
        logger.debug(f"Sent: {message}")

    async def subscribe(self, channel: ChannelType, tickers: List[str]) -> None:
        """
        Subscribe to a channel for specific tickers.

        Args:
            channel: Channel type to subscribe to
            tickers: List of market tickers
        """
        if not tickers:
            return

        # Track subscriptions
        if channel.value not in self._subscriptions:
            self._subscriptions[channel.value] = set()
        self._subscriptions[channel.value].update(tickers)

        message = {
            "id": self._next_cmd_id(),
            "cmd": "subscribe",
            "params": {
                "channels": [channel.value],
                "market_tickers": tickers,
            },
        }

        await self._send(message)
        logger.info(f"Subscribed to {channel.value} for {len(tickers)} tickers")

    async def unsubscribe(self, channel: ChannelType, tickers: List[str]) -> None:
        """
        Unsubscribe from a channel for specific tickers.

        Args:
            channel: Channel type to unsubscribe from
            tickers: List of market tickers
        """
        if not tickers:
            return

        # Update tracked subscriptions
        if channel.value in self._subscriptions:
            self._subscriptions[channel.value] -= set(tickers)

        message = {
            "id": self._next_cmd_id(),
            "cmd": "unsubscribe",
            "params": {
                "channels": [channel.value],
                "market_tickers": tickers,
            },
        }

        await self._send(message)
        logger.info(f"Unsubscribed from {channel.value} for {len(tickers)} tickers")

    def register_callback(
        self,
        message_type: MessageType,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        Register a callback for a specific message type.

        Args:
            message_type: Type of message to handle
            callback: Function to call with message data
        """
        if message_type.value not in self._callbacks:
            self._callbacks[message_type.value] = []
        self._callbacks[message_type.value].append(callback)
        logger.debug(f"Registered callback for {message_type.value}")

    def unregister_callback(
        self,
        message_type: MessageType,
        callback: Callable[[Dict[str, Any]], None],
    ) -> None:
        """
        Unregister a callback.

        Args:
            message_type: Type of message
            callback: Function to remove
        """
        if message_type.value in self._callbacks:
            try:
                self._callbacks[message_type.value].remove(callback)
                logger.debug(f"Unregistered callback for {message_type.value}")
            except ValueError:
                pass

    def _dispatch_message(self, message: Dict[str, Any]) -> None:
        """Dispatch a message to registered callbacks."""
        msg_type = message.get("type")
        if not msg_type:
            return

        callbacks = self._callbacks.get(msg_type, [])
        for callback in callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Callback error for {msg_type}: {e}")

    async def _receive_loop(self) -> None:
        """Main receive loop for WebSocket messages."""
        while self._running and self._websocket:
            try:
                raw_message = await self._websocket.recv()
                message = json.loads(raw_message)
                logger.debug(f"Received: {message}")
                self._dispatch_message(message)

            except ConnectionClosed as e:
                logger.warning(f"Connection closed: {e}")
                if self._running:
                    await self._reconnect()
                break

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse message: {e}")

            except Exception as e:
                logger.error(f"Receive error: {e}")
                if self._running:
                    await self._reconnect()
                break

    async def _reconnect(self) -> None:
        """Handle reconnection with exponential backoff."""
        delay = self._reconnect_delay
        attempts = 0

        while self._running:
            if self._reconnect_attempts > 0 and attempts >= self._reconnect_attempts:
                logger.error("Max reconnection attempts reached")
                self._running = False
                break

            attempts += 1
            logger.info(f"Reconnecting (attempt {attempts})...")

            try:
                await self.connect()

                # Resubscribe to all channels
                for channel, tickers in self._subscriptions.items():
                    if tickers:
                        await self.subscribe(ChannelType(channel), list(tickers))

                logger.info("Reconnected successfully")
                return

            except WebSocketException as e:
                logger.warning(f"Reconnection failed: {e}")

            await asyncio.sleep(delay)
            delay = min(delay * 2, self._reconnect_delay_max)

    async def run(self) -> None:
        """Start the WebSocket client and process messages."""
        await self.connect()
        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())
        logger.info("WebSocket client running")

    async def wait(self) -> None:
        """Wait for the client to stop."""
        if self._receive_task:
            await self._receive_task

    async def __aenter__(self) -> "KalshiWebSocketClient":
        """Async context manager entry."""
        await self.run()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
