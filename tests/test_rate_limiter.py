"""Tests for rate limiter."""

import asyncio
import time

import pytest

from src.api.rate_limiter import RateLimiter, RequestType, TokenBucket


class TestTokenBucket:
    """Tests for TokenBucket class."""

    def test_init_starts_full(self):
        """Test that bucket initializes with full capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=10)
        assert bucket.tokens == 10

    def test_try_acquire_success(self):
        """Test successful token acquisition."""
        bucket = TokenBucket(capacity=10, refill_rate=10)
        assert bucket.try_acquire(1) is True
        assert bucket.tokens == 9

    def test_try_acquire_failure(self):
        """Test failed token acquisition when empty."""
        bucket = TokenBucket(capacity=1, refill_rate=1)
        bucket.tokens = 0
        assert bucket.try_acquire(1) is False

    def test_try_acquire_multiple(self):
        """Test acquiring multiple tokens."""
        bucket = TokenBucket(capacity=10, refill_rate=10)
        assert bucket.try_acquire(5) is True
        assert bucket.tokens == 5

    @pytest.mark.asyncio
    async def test_acquire_no_wait_when_available(self):
        """Test acquire returns immediately when tokens available."""
        bucket = TokenBucket(capacity=10, refill_rate=10)
        wait_time = await bucket.acquire(1)
        assert wait_time == 0.0

    @pytest.mark.asyncio
    async def test_acquire_waits_when_empty(self):
        """Test acquire waits when tokens depleted."""
        bucket = TokenBucket(capacity=1, refill_rate=10)  # 10 tokens/sec
        bucket.tokens = 0

        start = time.monotonic()
        await bucket.acquire(1)
        elapsed = time.monotonic() - start

        # Should wait ~0.1 seconds for 1 token at 10/sec
        assert 0.05 < elapsed < 0.2

    def test_refill_adds_tokens(self):
        """Test that refill adds tokens based on elapsed time."""
        bucket = TokenBucket(capacity=10, refill_rate=10)
        bucket.tokens = 0
        bucket.last_refill = time.monotonic() - 0.5  # 0.5 sec ago

        bucket._refill()

        # Should have added ~5 tokens (0.5 sec * 10/sec)
        assert 4 < bucket.tokens < 6

    def test_refill_caps_at_capacity(self):
        """Test that refill doesn't exceed capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=100)
        bucket.tokens = 8
        bucket.last_refill = time.monotonic() - 1.0

        bucket._refill()

        assert bucket.tokens == 10  # Capped at capacity


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_init_default_limits(self):
        """Test default rate limits."""
        limiter = RateLimiter()
        assert limiter._read_bucket.capacity == 20
        assert limiter._write_bucket.capacity == 10

    def test_init_custom_limits(self):
        """Test custom rate limits."""
        limiter = RateLimiter(read_limit=50, write_limit=25)
        assert limiter._read_bucket.capacity == 50
        assert limiter._write_bucket.capacity == 25

    @pytest.mark.asyncio
    async def test_acquire_read(self):
        """Test acquiring read token."""
        limiter = RateLimiter(read_limit=20, write_limit=10)
        wait_time = await limiter.acquire_read()
        assert wait_time == 0.0

    @pytest.mark.asyncio
    async def test_acquire_write(self):
        """Test acquiring write token."""
        limiter = RateLimiter(read_limit=20, write_limit=10)
        wait_time = await limiter.acquire_write()
        assert wait_time == 0.0

    @pytest.mark.asyncio
    async def test_acquire_by_type_read(self):
        """Test acquire with READ type."""
        limiter = RateLimiter()
        wait_time = await limiter.acquire(RequestType.READ)
        assert wait_time == 0.0

    @pytest.mark.asyncio
    async def test_acquire_by_type_write(self):
        """Test acquire with WRITE type."""
        limiter = RateLimiter()
        wait_time = await limiter.acquire(RequestType.WRITE)
        assert wait_time == 0.0

    @pytest.mark.asyncio
    async def test_read_write_independent(self):
        """Test that read and write buckets are independent."""
        limiter = RateLimiter(read_limit=5, write_limit=5)

        # Exhaust read tokens
        for _ in range(5):
            await limiter.acquire_read()

        # Write should still be available
        start = time.monotonic()
        await limiter.acquire_write()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # Should be immediate

    def test_tokens_available(self):
        """Test checking available tokens."""
        limiter = RateLimiter(read_limit=10, write_limit=5)
        assert limiter.read_tokens_available == 10
        assert limiter.write_tokens_available == 5

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self):
        """Test that rate limiting actually limits requests."""
        limiter = RateLimiter(read_limit=10, write_limit=10)

        # Exhaust all tokens
        for _ in range(10):
            await limiter.acquire_read()

        # Next acquire should wait
        start = time.monotonic()
        await limiter.acquire_read()
        elapsed = time.monotonic() - start

        assert elapsed > 0.05  # Should have waited

    @pytest.mark.asyncio
    async def test_concurrent_acquires(self):
        """Test concurrent token acquisition."""
        limiter = RateLimiter(read_limit=5, write_limit=5)

        async def acquire_read():
            await limiter.acquire_read()

        # Run 5 concurrent acquires
        await asyncio.gather(*[acquire_read() for _ in range(5)])

        # All 5 should succeed immediately, 6th should wait
        assert limiter.read_tokens_available < 1
