"""
Mock REST client interface for Kalshi API.

This module defines the interface that the actual REST client (built in another
worktree) will implement. For testing purposes, we also provide a mock implementation.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol

from .models import Market, OrderBook


class KalshiClientProtocol(Protocol):
    """Protocol defining the expected REST client interface."""

    async def get_markets(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[List[Market], Optional[str]]:
        """
        Fetch markets from the API.

        Args:
            status: Filter by market status ('active', 'closed', etc.)
            category: Filter by category
            limit: Maximum number of markets to return
            cursor: Pagination cursor

        Returns:
            Tuple of (list of markets, next cursor or None)
        """
        ...

    async def get_orderbook(self, ticker: str, depth: int = 10) -> OrderBook:
        """
        Fetch the order book for a specific market.

        Args:
            ticker: Market ticker symbol
            depth: Number of price levels to fetch

        Returns:
            OrderBook for the market
        """
        ...

    async def get_market(self, ticker: str) -> Market:
        """
        Fetch a single market by ticker.

        Args:
            ticker: Market ticker symbol

        Returns:
            Market data
        """
        ...


class BaseKalshiClient(ABC):
    """Abstract base class for Kalshi API clients."""

    @abstractmethod
    async def get_markets(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> tuple[List[Market], Optional[str]]:
        """Fetch markets from the API."""
        pass

    @abstractmethod
    async def get_orderbook(self, ticker: str, depth: int = 10) -> OrderBook:
        """Fetch the order book for a specific market."""
        pass

    @abstractmethod
    async def get_market(self, ticker: str) -> Market:
        """Fetch a single market by ticker."""
        pass

    async def get_all_markets(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Market]:
        """
        Fetch all markets by paginating through results.

        Args:
            status: Filter by market status
            category: Filter by category

        Returns:
            Complete list of markets matching filters
        """
        all_markets: List[Market] = []
        cursor: Optional[str] = None

        while True:
            markets, cursor = await self.get_markets(
                status=status,
                category=category,
                limit=100,
                cursor=cursor,
            )
            all_markets.extend(markets)

            if cursor is None:
                break

        return all_markets
