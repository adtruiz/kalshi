"""API client module."""

from src.api.rate_limiter import RateLimiter, RequestType
from src.api.rest_client import KalshiAPIError, KalshiRestClient
from src.api.websocket_client import (
    ChannelType,
    KalshiWebSocketClient,
    MessageType,
)

# Mock clients for testing
from src.api.client import BaseKalshiClient, KalshiClientProtocol
from src.api.mock_client import MockKalshiClient, create_sample_markets, create_sample_orderbook
from src.api.models import Market as MockMarket, OrderBook as MockOrderBook, OrderBookLevel as MockOrderBookLevel

__all__ = [
    # Real clients
    "RateLimiter",
    "RequestType",
    "KalshiRestClient",
    "KalshiAPIError",
    "KalshiWebSocketClient",
    "ChannelType",
    "MessageType",
    # Mock clients for testing
    "BaseKalshiClient",
    "KalshiClientProtocol",
    "MockKalshiClient",
    "MockMarket",
    "MockOrderBook",
    "MockOrderBookLevel",
    "create_sample_markets",
    "create_sample_orderbook",
]
