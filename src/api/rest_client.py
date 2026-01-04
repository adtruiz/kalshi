"""Async REST client for Kalshi API."""

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp

from config.settings import Settings, get_settings
from src.api.rate_limiter import RateLimiter, RequestType
from src.auth.kalshi_auth import KalshiAuth
from src.models import (
    BalanceResponse,
    CreateOrderRequest,
    Market,
    Order,
    OrderBook,
    OrderBookLevel,
    Position,
)
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.rest_client")


class KalshiAPIError(Exception):
    """Exception for Kalshi API errors."""

    def __init__(self, status: int, message: str, code: Optional[str] = None) -> None:
        self.status = status
        self.message = message
        self.code = code
        super().__init__(f"[{status}] {code or 'ERROR'}: {message}")


class KalshiRestClient:
    """Async REST client for Kalshi API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        """
        Initialize REST client.

        Args:
            settings: Application settings (uses default if not provided)
            session: aiohttp session (creates new if not provided)
        """
        self._settings = settings or get_settings()
        self._session = session
        self._owns_session = session is None
        self._auth = KalshiAuth(
            api_key=self._settings.kalshi_api_key,
            private_key_path=self._settings.private_key_path,
        )
        self._rate_limiter = RateLimiter(
            read_limit=self._settings.read_rate_limit,
            write_limit=self._settings.write_rate_limit,
        )
        self._base_url = self._settings.base_url
        logger.info(f"REST client initialized for {self._base_url}")

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Close the client session."""
        if self._session and self._owns_session and not self._session.closed:
            await self._session.close()
            logger.debug("REST client session closed")

    async def __aenter__(self) -> "KalshiRestClient":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    def _get_path(self, endpoint: str) -> str:
        """Get API path for signing (without base URL)."""
        # Parse base URL to get path prefix
        parsed = urlparse(self._base_url)
        return f"{parsed.path}/{endpoint.lstrip('/')}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        request_type: RequestType = RequestType.READ,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base URL)
            request_type: Type for rate limiting
            params: Query parameters
            json_data: JSON body data

        Returns:
            Response JSON data

        Raises:
            KalshiAPIError: On API errors
        """
        session = await self._ensure_session()

        # Rate limiting
        await self._rate_limiter.acquire(request_type)

        # Build URL
        url = urljoin(self._base_url + "/", endpoint.lstrip("/"))

        # Get auth headers (path without query params)
        path = self._get_path(endpoint)
        auth_headers = self._auth.get_auth_headers(method, path)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **auth_headers,
        }

        logger.debug(f"Request: {method} {url}")

        async with session.request(
            method, url, headers=headers, params=params, json=json_data
        ) as response:
            try:
                data = await response.json()
            except aiohttp.ContentTypeError:
                data = {}

            if response.status >= 400:
                error_msg = data.get("message", "Unknown error")
                error_code = data.get("code")
                logger.error(f"API error: {response.status} - {error_msg}")
                raise KalshiAPIError(response.status, error_msg, error_code)

            return data

    # ==================== Market Endpoints ====================

    async def get_markets(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        event_ticker: Optional[str] = None,
    ) -> tuple[List[Market], Optional[str]]:
        """
        Get list of markets.

        Args:
            status: Filter by status (open, closed, settled)
            limit: Maximum number of markets to return
            cursor: Pagination cursor
            event_ticker: Filter by event ticker

        Returns:
            Tuple of (markets list, next cursor)
        """
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        if event_ticker:
            params["event_ticker"] = event_ticker

        data = await self._request("GET", "markets", params=params)

        markets = [Market(**m) for m in data.get("markets", [])]
        next_cursor = data.get("cursor")

        logger.debug(f"Fetched {len(markets)} markets")
        return markets, next_cursor

    async def get_market(self, ticker: str) -> Market:
        """
        Get a single market by ticker.

        Args:
            ticker: Market ticker

        Returns:
            Market object
        """
        data = await self._request("GET", f"markets/{ticker}")
        market = Market(**data.get("market", data))
        logger.debug(f"Fetched market: {ticker}")
        return market

    async def get_orderbook(self, ticker: str, depth: int = 10) -> OrderBook:
        """
        Get orderbook for a market.

        Args:
            ticker: Market ticker
            depth: Number of price levels

        Returns:
            OrderBook object
        """
        data = await self._request(
            "GET", f"markets/{ticker}/orderbook", params={"depth": depth}
        )

        orderbook_data = data.get("orderbook", data)

        # Parse order book levels
        yes_bids = [
            OrderBookLevel(price=level[0], count=level[1])
            for level in orderbook_data.get("yes", [[]])[0] or []
        ] if orderbook_data.get("yes") else []

        yes_asks = [
            OrderBookLevel(price=level[0], count=level[1])
            for level in orderbook_data.get("yes", [[], []])[1] or []
        ] if orderbook_data.get("yes") and len(orderbook_data.get("yes", [])) > 1 else []

        no_bids = [
            OrderBookLevel(price=level[0], count=level[1])
            for level in orderbook_data.get("no", [[]])[0] or []
        ] if orderbook_data.get("no") else []

        no_asks = [
            OrderBookLevel(price=level[0], count=level[1])
            for level in orderbook_data.get("no", [[], []])[1] or []
        ] if orderbook_data.get("no") and len(orderbook_data.get("no", [])) > 1 else []

        orderbook = OrderBook(
            ticker=ticker,
            yes_bids=yes_bids,
            yes_asks=yes_asks,
            no_bids=no_bids,
            no_asks=no_asks,
        )

        logger.debug(f"Fetched orderbook for: {ticker}")
        return orderbook

    # ==================== Order Endpoints ====================

    async def create_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        price: Optional[int] = None,
        order_type: str = "limit",
    ) -> Order:
        """
        Create a new order.

        Args:
            ticker: Market ticker
            side: Order side (yes/no)
            action: Order action (buy/sell)
            count: Number of contracts
            price: Limit price in cents (required for limit orders)
            order_type: Order type (limit/market)

        Returns:
            Created Order object
        """
        request_data: Dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": order_type,
        }

        if order_type == "limit" and price is not None:
            if side == "yes":
                request_data["yes_price"] = price
            else:
                request_data["no_price"] = price

        data = await self._request(
            "POST", "portfolio/orders", request_type=RequestType.WRITE, json_data=request_data
        )

        order = Order(**data.get("order", data))
        logger.info(f"Created order: {order.order_id} ({side} {action} {count}@{price})")
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        try:
            await self._request(
                "DELETE", f"portfolio/orders/{order_id}", request_type=RequestType.WRITE
            )
            logger.info(f"Cancelled order: {order_id}")
            return True
        except KalshiAPIError as e:
            if e.status == 404:
                logger.warning(f"Order not found: {order_id}")
                return False
            raise

    async def get_orders(
        self,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[List[Order], Optional[str]]:
        """
        Get list of orders.

        Args:
            status: Filter by status (resting, pending, executed, canceled)
            ticker: Filter by market ticker
            limit: Maximum number of orders
            cursor: Pagination cursor

        Returns:
            Tuple of (orders list, next cursor)
        """
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if ticker:
            params["ticker"] = ticker
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "portfolio/orders", params=params)

        orders = [Order(**o) for o in data.get("orders", [])]
        next_cursor = data.get("cursor")

        logger.debug(f"Fetched {len(orders)} orders")
        return orders, next_cursor

    # ==================== Portfolio Endpoints ====================

    async def get_balance(self) -> float:
        """
        Get account balance.

        Returns:
            Balance in dollars (converted from cents)
        """
        data = await self._request("GET", "portfolio/balance")
        balance_cents = data.get("balance", 0)
        balance_dollars = balance_cents / 100.0
        logger.debug(f"Account balance: ${balance_dollars:.2f}")
        return balance_dollars

    async def get_positions(
        self,
        ticker: Optional[str] = None,
        event_ticker: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[List[Position], Optional[str]]:
        """
        Get list of positions.

        Args:
            ticker: Filter by market ticker
            event_ticker: Filter by event ticker
            limit: Maximum number of positions
            cursor: Pagination cursor

        Returns:
            Tuple of (positions list, next cursor)
        """
        params: Dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "portfolio/positions", params=params)

        positions = [Position(**p) for p in data.get("market_positions", [])]
        next_cursor = data.get("cursor")

        logger.debug(f"Fetched {len(positions)} positions")
        return positions, next_cursor
