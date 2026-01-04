"""API client module."""

from src.api.rate_limiter import RateLimiter, RequestType
from src.api.rest_client import KalshiAPIError, KalshiRestClient
from src.api.websocket_client import (
    ChannelType,
    KalshiWebSocketClient,
    MessageType,
)

# Mock clients for scanner testing
from src.api.client import BaseKalshiClient, KalshiClientProtocol
from src.api.mock_client import MockKalshiClient, create_sample_markets, create_sample_orderbook
from src.api.models import Market as MockMarket, OrderBook as MockOrderBook, OrderBookLevel as MockOrderBookLevel

# Mock clients for execution testing
from src.api.mock_clients import (
    Balance,
    Fill,
    MockRestClient,
    MockWebSocketClient,
    Order as MockOrder,
    OrderAction as MockOrderAction,
    OrderSide as MockOrderSide,
    OrderStatus as MockOrderStatus,
    Position as MockPosition,
    SpreadOpportunity as MockSpreadOpportunity,
)

__all__ = [
    # Real clients
    "RateLimiter",
    "RequestType",
    "KalshiRestClient",
    "KalshiAPIError",
    "KalshiWebSocketClient",
    "ChannelType",
    "MessageType",
    # Mock clients for scanner testing
    "BaseKalshiClient",
    "KalshiClientProtocol",
    "MockKalshiClient",
    "MockMarket",
    "MockOrderBook",
    "MockOrderBookLevel",
    "create_sample_markets",
    "create_sample_orderbook",
    # Mock clients for execution testing
    "Balance",
    "Fill",
    "MockRestClient",
    "MockWebSocketClient",
    "MockOrder",
    "MockOrderAction",
    "MockOrderSide",
    "MockOrderStatus",
    "MockPosition",
    "MockSpreadOpportunity",
]
