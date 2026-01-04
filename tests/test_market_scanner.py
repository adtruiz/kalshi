"""Tests for MarketScanner class."""

from datetime import datetime, timedelta

import pytest

from config.strategy_params import StrategyParams
from src.api.mock_client import MockKalshiClient, create_sample_markets
from src.api.models import Market
from src.scanner.market_scanner import MarketScanner


class TestMarketScanner:
    """Tests for MarketScanner class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return StrategyParams(
            min_spread_cents=3,
            max_spread_cents=15,
            min_days_to_expiration=3,
            min_liquidity=1000,
            max_liquidity=100000,
            min_volume_24h=100,
        )

    @pytest.fixture
    def mock_client(self):
        """Create mock Kalshi client."""
        return MockKalshiClient()

    @pytest.fixture
    def scanner(self, mock_client, config):
        """Create scanner with mock client."""
        return MarketScanner(mock_client, config)

    @pytest.mark.asyncio
    async def test_scan_markets_filters_by_expiration(self, scanner, mock_client):
        """Test that markets expiring too soon are filtered out."""
        now = datetime.utcnow()

        # Add markets with different expirations
        mock_client.add_market(Market(
            ticker="SOON",
            title="Expires soon",
            status="active",
            expiration_time=now + timedelta(days=1),  # Too soon
            close_time=now + timedelta(days=1),
            volume_24h=500,
            liquidity=5000,
        ))
        mock_client.add_market(Market(
            ticker="LATER",
            title="Expires later",
            status="active",
            expiration_time=now + timedelta(days=10),  # Good
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        ))

        markets = await scanner.scan_markets(reference_time=now)

        assert len(markets) == 1
        assert markets[0].ticker == "LATER"

    @pytest.mark.asyncio
    async def test_scan_markets_filters_by_volume(self, scanner, mock_client):
        """Test that low volume markets are filtered out."""
        now = datetime.utcnow()

        mock_client.add_market(Market(
            ticker="LOW_VOL",
            title="Low volume",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=50,  # Too low
            liquidity=5000,
        ))
        mock_client.add_market(Market(
            ticker="HIGH_VOL",
            title="High volume",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,  # Good
            liquidity=5000,
        ))

        markets = await scanner.scan_markets(reference_time=now)

        assert len(markets) == 1
        assert markets[0].ticker == "HIGH_VOL"

    @pytest.mark.asyncio
    async def test_scan_markets_only_active(self, scanner, mock_client):
        """Test that only active markets are returned."""
        now = datetime.utcnow()

        mock_client.add_market(Market(
            ticker="ACTIVE",
            title="Active market",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        ))
        mock_client.add_market(Market(
            ticker="CLOSED",
            title="Closed market",
            status="closed",
            expiration_time=now - timedelta(days=1),
            close_time=now - timedelta(days=1),
            volume_24h=0,
            liquidity=0,
        ))

        markets = await scanner.scan_markets(reference_time=now)

        assert len(markets) == 1
        assert markets[0].ticker == "ACTIVE"

    def test_filter_by_liquidity_too_low(self, scanner):
        """Test that low liquidity markets are filtered out."""
        now = datetime.utcnow()

        markets = [
            Market(
                ticker="LOW_LIQ",
                title="Low liquidity",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=500,  # Below min_liquidity (1000)
            ),
            Market(
                ticker="GOOD_LIQ",
                title="Good liquidity",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=5000,  # Good
            ),
        ]

        filtered = scanner.filter_by_liquidity(markets)

        assert len(filtered) == 1
        assert filtered[0].ticker == "GOOD_LIQ"

    def test_filter_by_liquidity_too_high(self, scanner):
        """Test that high liquidity markets are filtered out."""
        now = datetime.utcnow()

        markets = [
            Market(
                ticker="HIGH_LIQ",
                title="High liquidity",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=500000,  # Above max_liquidity (100000)
            ),
            Market(
                ticker="GOOD_LIQ",
                title="Good liquidity",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=50000,  # Good
            ),
        ]

        filtered = scanner.filter_by_liquidity(markets)

        assert len(filtered) == 1
        assert filtered[0].ticker == "GOOD_LIQ"

    def test_filter_by_liquidity_range(self, scanner):
        """Test that liquidity filtering preserves correct range."""
        now = datetime.utcnow()

        markets = [
            Market(
                ticker="AT_MIN",
                title="At minimum",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=1000,  # Exactly at min
            ),
            Market(
                ticker="AT_MAX",
                title="At maximum",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=100000,  # Exactly at max
            ),
            Market(
                ticker="MID_RANGE",
                title="Mid range",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500,
                liquidity=50000,  # Middle of range
            ),
        ]

        filtered = scanner.filter_by_liquidity(markets)

        assert len(filtered) == 3  # All should pass

    @pytest.mark.asyncio
    async def test_get_tradeable_markets(self, scanner, mock_client):
        """Test getting markets that pass all filters."""
        now = datetime.utcnow()

        # Add various markets
        mock_client.add_market(Market(
            ticker="PERFECT",
            title="Perfect market",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        ))
        mock_client.add_market(Market(
            ticker="BAD_EXP",
            title="Bad expiration",
            status="active",
            expiration_time=now + timedelta(days=1),
            close_time=now + timedelta(days=1),
            volume_24h=500,
            liquidity=5000,
        ))
        mock_client.add_market(Market(
            ticker="BAD_LIQ",
            title="Bad liquidity",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=500,  # Too low
        ))

        markets = await scanner.get_tradeable_markets(reference_time=now)

        assert len(markets) == 1
        assert markets[0].ticker == "PERFECT"

    @pytest.mark.asyncio
    async def test_scan_with_category_filter(self, scanner, mock_client):
        """Test filtering by category."""
        now = datetime.utcnow()

        mock_client.add_market(Market(
            ticker="CRYPTO1",
            title="Crypto market",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
            category="crypto",
        ))
        mock_client.add_market(Market(
            ticker="POLITICS1",
            title="Politics market",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
            category="politics",
        ))

        markets = await scanner.scan_markets(category="crypto", reference_time=now)

        assert len(markets) == 1
        assert markets[0].ticker == "CRYPTO1"

    def test_update_config(self, scanner, mock_client):
        """Test updating scanner configuration."""
        new_config = StrategyParams(
            min_spread_cents=5,
            min_days_to_expiration=7,
            min_volume_24h=200,
        )

        scanner.update_config(new_config)

        assert scanner.config.min_spread_cents == 5
        assert scanner.config.min_days_to_expiration == 7
        assert scanner.config.min_volume_24h == 200

    @pytest.mark.asyncio
    async def test_scan_with_sample_data(self, config, mock_client):
        """Test scanning with realistic sample data."""
        scanner = MarketScanner(mock_client, config)

        # Load sample markets
        for market in create_sample_markets():
            mock_client.add_market(market)

        markets = await scanner.get_tradeable_markets()

        # Should filter out:
        # - KXSPY (expires in 1 day)
        # - KXLOW (volume 50 < 100)
        # - KXCLOSED (status = closed)
        # - KXPOP (liquidity 500000 > 100000)
        # Should keep:
        # - KXBTC (good)
        # - KXETH (good)
        # - KXRAIN (good)

        tickers = [m.ticker for m in markets]
        assert "KXBTC-24JAN15-T50000" in tickers
        assert "KXETH-24JAN20-T3000" in tickers
        assert "KXRAIN-24JAN10-NYC" in tickers
        assert "KXSPY-24JAN05-T475" not in tickers
        assert "KXLOW-24JAN20-VOL" not in tickers
        assert "KXCLOSED-24JAN01" not in tickers
        assert "KXPOP-24JAN25-HIGH" not in tickers
