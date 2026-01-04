"""Token bucket rate limiter for Kalshi API."""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.rate_limiter")


class RequestType(str, Enum):
    """Type of API request for rate limiting."""
    READ = "read"
    WRITE = "write"


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""

    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.monotonic)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        """Initialize bucket with full capacity."""
        self.tokens = self.capacity

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    async def acquire(self, tokens: float = 1.0) -> float:
        """
        Acquire tokens, waiting if necessary.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Time waited in seconds
        """
        async with self._lock:
            self._refill()

            wait_time = 0.0
            if self.tokens < tokens:
                # Calculate wait time needed
                deficit = tokens - self.tokens
                wait_time = deficit / self.refill_rate
                logger.debug(f"Rate limit reached, waiting {wait_time:.3f}s")
                await asyncio.sleep(wait_time)
                self._refill()

            self.tokens -= tokens
            return wait_time

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """
        Try to acquire tokens without waiting.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False otherwise
        """
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


class RateLimiter:
    """
    Rate limiter for Kalshi API with separate limits for read and write operations.

    Kalshi Basic tier limits:
    - Read: 20 requests/second
    - Write: 10 requests/second
    """

    def __init__(
        self,
        read_limit: int = 20,
        write_limit: int = 10,
    ) -> None:
        """
        Initialize rate limiter.

        Args:
            read_limit: Maximum read requests per second
            write_limit: Maximum write requests per second
        """
        self._read_bucket = TokenBucket(capacity=read_limit, refill_rate=read_limit)
        self._write_bucket = TokenBucket(capacity=write_limit, refill_rate=write_limit)
        logger.info(f"Rate limiter initialized: read={read_limit}/s, write={write_limit}/s")

    async def acquire_read(self) -> float:
        """
        Acquire a read request slot.

        Returns:
            Time waited in seconds
        """
        wait_time = await self._read_bucket.acquire()
        if wait_time > 0:
            logger.debug(f"Read request waited {wait_time:.3f}s due to rate limit")
        return wait_time

    async def acquire_write(self) -> float:
        """
        Acquire a write request slot.

        Returns:
            Time waited in seconds
        """
        wait_time = await self._write_bucket.acquire()
        if wait_time > 0:
            logger.debug(f"Write request waited {wait_time:.3f}s due to rate limit")
        return wait_time

    async def acquire(self, request_type: RequestType) -> float:
        """
        Acquire a request slot based on type.

        Args:
            request_type: Type of request (read/write)

        Returns:
            Time waited in seconds
        """
        if request_type == RequestType.READ:
            return await self.acquire_read()
        return await self.acquire_write()

    @property
    def read_tokens_available(self) -> float:
        """Get available read tokens."""
        self._read_bucket._refill()
        return self._read_bucket.tokens

    @property
    def write_tokens_available(self) -> float:
        """Get available write tokens."""
        self._write_bucket._refill()
        return self._write_bucket.tokens
