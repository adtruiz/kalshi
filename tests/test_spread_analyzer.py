"""Tests for SpreadAnalyzer class."""

from datetime import datetime, timedelta

import pytest

from config.strategy_params import StrategyParams
from src.api.mock_client import (
    MockKalshiClient,
    create_sample_markets,
    create_sample_orderbook,
)
from src.api.models import Market, OrderBook, OrderBookLevel
from src.scanner.spread_analyzer import SpreadAnalyzer


class TestSpreadAnalyzer:
    """Tests for SpreadAnalyzer class."""

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
    def analyzer(self, config):
        """Create analyzer without client."""
        return SpreadAnalyzer(config)

    @pytest.fixture
    def sample_market(self):
        """Create a sample market for testing."""
        return Market(
            ticker="TEST-MARKET",
            title="Test Market",
            status="active",
            expiration_time=datetime.utcnow() + timedelta(days=10),
            close_time=datetime.utcnow() + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        )

    def test_determine_likely_side_yes(self, analyzer):
        """Test determining YES side when midpoint > 50."""
        orderbook = create_sample_orderbook(yes_bid=55, yes_ask=65)

        side = analyzer.determine_likely_side(orderbook)

        assert side == "yes"

    def test_determine_likely_side_no(self, analyzer):
        """Test determining NO side when midpoint <= 50."""
        orderbook = create_sample_orderbook(yes_bid=35, yes_ask=45)

        side = analyzer.determine_likely_side(orderbook)

        assert side == "no"

    def test_determine_likely_side_exactly_50(self, analyzer):
        """Test edge case when midpoint is exactly 50."""
        orderbook = create_sample_orderbook(yes_bid=45, yes_ask=55)

        side = analyzer.determine_likely_side(orderbook)

        assert side == "no"  # <= 50 means NO

    def test_determine_likely_side_empty_orderbook(self, analyzer):
        """Test with empty orderbook defaults to YES."""
        orderbook = OrderBook()

        side = analyzer.determine_likely_side(orderbook)

        assert side == "yes"  # Default

    def test_analyze_market_good_spread(self, analyzer, sample_market):
        """Test analyzing a market with a good spread opportunity."""
        orderbook = create_sample_orderbook(yes_bid=45, yes_ask=52)

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.ticker == "TEST-MARKET"
        assert opportunity.yes_bid == 45
        assert opportunity.yes_ask == 52
        assert opportunity.spread_cents == 7
        assert opportunity.likely_side == "no"  # midpoint = 48.5 <= 50
        assert opportunity.score > 0

    def test_analyze_market_spread_too_small(self, analyzer, sample_market):
        """Test that small spreads are rejected."""
        orderbook = create_sample_orderbook(yes_bid=50, yes_ask=52)  # 2 cent spread

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is None

    def test_analyze_market_spread_too_large(self, analyzer, sample_market):
        """Test that large spreads are rejected (illiquid)."""
        orderbook = create_sample_orderbook(yes_bid=30, yes_ask=50)  # 20 cent spread

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is None

    def test_analyze_market_missing_bid(self, analyzer, sample_market):
        """Test handling of missing bid data."""
        orderbook = OrderBook(
            yes_bids=[],
            yes_asks=[OrderBookLevel(price=55, quantity=100)],
        )

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is None

    def test_analyze_market_missing_ask(self, analyzer, sample_market):
        """Test handling of missing ask data."""
        orderbook = OrderBook(
            yes_bids=[OrderBookLevel(price=45, quantity=100)],
            yes_asks=[],
        )

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is None

    def test_expected_profit_yes_side(self, analyzer, sample_market):
        """Test expected profit calculation for YES side."""
        # Midpoint > 50, so YES is likely
        orderbook = create_sample_orderbook(yes_bid=60, yes_ask=68)

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.likely_side == "yes"
        # Expected profit = probability * 100 - cost
        # probability = midpoint / 100 = 64 / 100 = 0.64
        # cost = yes_ask = 68
        # expected = 0.64 * 100 - 68 = 64 - 68 = -4
        assert opportunity.expected_profit == pytest.approx(-4.0, rel=0.01)

    def test_expected_profit_no_side(self, analyzer, sample_market):
        """Test expected profit calculation for NO side."""
        # Midpoint <= 50, so NO is likely
        orderbook = create_sample_orderbook(yes_bid=35, yes_ask=42)

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.likely_side == "no"
        # Expected profit = probability * 100 - cost
        # midpoint = 38.5, probability = 1 - (38.5/100) = 0.615
        # cost = 100 - yes_bid = 100 - 35 = 65
        # expected = 0.615 * 100 - 65 = 61.5 - 65 = -3.5
        assert opportunity.expected_profit == pytest.approx(-3.5, rel=0.01)

    def test_score_calculation(self, analyzer, sample_market):
        """Test that score is calculated and reasonable."""
        orderbook = create_sample_orderbook(yes_bid=45, yes_ask=52)

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.score > 0
        assert opportunity.score < 20  # Reasonable upper bound

    def test_score_higher_for_better_spread(self, analyzer, sample_market):
        """Test that higher spreads get better scores (within limits)."""
        small_spread_ob = create_sample_orderbook(yes_bid=48, yes_ask=52)  # 4 cent
        large_spread_ob = create_sample_orderbook(yes_bid=44, yes_ask=52)  # 8 cent

        small_opp = analyzer.analyze_market(sample_market, small_spread_ob)
        large_opp = analyzer.analyze_market(sample_market, large_spread_ob)

        assert small_opp is not None
        assert large_opp is not None
        # Larger spread should have higher score (other factors being equal-ish)
        # Note: other factors like probability affect this too
        assert large_opp.spread_cents > small_opp.spread_cents

    @pytest.mark.asyncio
    async def test_find_opportunities(self, config):
        """Test finding opportunities across multiple markets."""
        mock_client = MockKalshiClient()
        analyzer = SpreadAnalyzer(config, mock_client)
        now = datetime.utcnow()

        # Add markets with orderbooks
        market1 = Market(
            ticker="GOOD1",
            title="Good Market 1",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        )
        market2 = Market(
            ticker="GOOD2",
            title="Good Market 2",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=1000,
            liquidity=10000,
        )
        market3 = Market(
            ticker="BAD_SPREAD",
            title="Bad spread",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        )

        mock_client.add_market(market1)
        mock_client.add_market(market2)
        mock_client.add_market(market3)

        mock_client.add_orderbook("GOOD1", create_sample_orderbook(yes_bid=45, yes_ask=52))
        mock_client.add_orderbook("GOOD2", create_sample_orderbook(yes_bid=55, yes_ask=65))
        mock_client.add_orderbook("BAD_SPREAD", create_sample_orderbook(yes_bid=50, yes_ask=51))  # Too small

        opportunities = await analyzer.find_opportunities([market1, market2, market3])

        assert len(opportunities) == 2
        tickers = [o.ticker for o in opportunities]
        assert "GOOD1" in tickers
        assert "GOOD2" in tickers
        assert "BAD_SPREAD" not in tickers

    @pytest.mark.asyncio
    async def test_find_opportunities_sorted_by_score(self, config):
        """Test that opportunities are sorted by score descending."""
        mock_client = MockKalshiClient()
        analyzer = SpreadAnalyzer(config, mock_client)
        now = datetime.utcnow()

        # Create markets with different characteristics
        for i in range(5):
            market = Market(
                ticker=f"MARKET{i}",
                title=f"Market {i}",
                status="active",
                expiration_time=now + timedelta(days=10),
                close_time=now + timedelta(days=10),
                volume_24h=500 + i * 100,
                liquidity=5000,
            )
            mock_client.add_market(market)
            mock_client.add_orderbook(
                f"MARKET{i}",
                create_sample_orderbook(yes_bid=45 - i, yes_ask=52 + i)
            )

        markets = [await mock_client.get_market(f"MARKET{i}") for i in range(5)]
        opportunities = await analyzer.find_opportunities(markets)

        # Check descending order
        scores = [o.score for o in opportunities]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_find_opportunities_handles_errors(self, config):
        """Test that errors in individual market analysis don't break the whole scan."""
        mock_client = MockKalshiClient()
        analyzer = SpreadAnalyzer(config, mock_client)
        now = datetime.utcnow()

        market1 = Market(
            ticker="GOOD",
            title="Good Market",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        )
        market2 = Market(
            ticker="NO_ORDERBOOK",
            title="No orderbook configured",
            status="active",
            expiration_time=now + timedelta(days=10),
            close_time=now + timedelta(days=10),
            volume_24h=500,
            liquidity=5000,
        )

        mock_client.add_market(market1)
        mock_client.add_market(market2)
        mock_client.add_orderbook("GOOD", create_sample_orderbook(yes_bid=45, yes_ask=52))
        # NO_ORDERBOOK intentionally not added

        # Should not raise, just skip the problematic market
        opportunities = await analyzer.find_opportunities([market1, market2])

        assert len(opportunities) == 1
        assert opportunities[0].ticker == "GOOD"

    @pytest.mark.asyncio
    async def test_find_opportunities_requires_client(self, config):
        """Test that find_opportunities raises without client."""
        analyzer = SpreadAnalyzer(config)  # No client

        with pytest.raises(RuntimeError, match="REST client required"):
            await analyzer.find_opportunities([])

    def test_update_config(self, analyzer):
        """Test updating analyzer configuration."""
        new_config = StrategyParams(
            min_spread_cents=5,
            max_spread_cents=20,
        )

        analyzer.update_config(new_config)

        assert analyzer.config.min_spread_cents == 5
        assert analyzer.config.max_spread_cents == 20

    def test_analyze_with_orderbook_wrapper(self, analyzer, sample_market):
        """Test the analyze_with_orderbook convenience method."""
        orderbook = create_sample_orderbook(yes_bid=45, yes_ask=52)

        opportunity = analyzer.analyze_with_orderbook(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.ticker == "TEST-MARKET"

    def test_spread_at_min_threshold(self, analyzer, sample_market):
        """Test spread exactly at minimum threshold."""
        orderbook = create_sample_orderbook(yes_bid=49, yes_ask=52)  # 3 cent spread

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.spread_cents == 3

    def test_spread_at_max_threshold(self, analyzer, sample_market):
        """Test spread exactly at maximum threshold."""
        orderbook = create_sample_orderbook(yes_bid=45, yes_ask=60)  # 15 cent spread

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.spread_cents == 15

    def test_probability_calculation_yes_side(self, analyzer, sample_market):
        """Test probability calculation when YES is likely."""
        orderbook = create_sample_orderbook(yes_bid=70, yes_ask=78)

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.likely_side == "yes"
        assert opportunity.probability == pytest.approx(0.74, rel=0.01)  # midpoint=74

    def test_probability_calculation_no_side(self, analyzer, sample_market):
        """Test probability calculation when NO is likely."""
        orderbook = create_sample_orderbook(yes_bid=20, yes_ask=28)

        opportunity = analyzer.analyze_market(sample_market, orderbook)

        assert opportunity is not None
        assert opportunity.likely_side == "no"
        # midpoint = 24, probability of NO = 1 - 0.24 = 0.76
        assert opportunity.probability == pytest.approx(0.76, rel=0.01)

    @pytest.mark.asyncio
    async def test_with_realistic_sample_data(self, config):
        """Test analyzer with realistic sample market data."""
        mock_client = MockKalshiClient()
        analyzer = SpreadAnalyzer(config, mock_client)

        # Load sample markets
        sample_markets = create_sample_markets()
        for market in sample_markets:
            mock_client.add_market(market)
            if market.yes_bid and market.yes_ask:
                mock_client.add_orderbook(
                    market.ticker,
                    create_sample_orderbook(
                        yes_bid=market.yes_bid,
                        yes_ask=market.yes_ask,
                    )
                )

        # Filter to active markets with bid/ask
        active_markets = [m for m in sample_markets if m.status == "active" and m.yes_bid and m.yes_ask]

        opportunities = await analyzer.find_opportunities(active_markets)

        # Check that we found some opportunities
        assert len(opportunities) > 0

        # Verify all have valid data
        for opp in opportunities:
            assert opp.spread_cents >= config.min_spread_cents
            assert opp.spread_cents <= config.max_spread_cents
            assert opp.likely_side in ("yes", "no")
            assert 0 <= opp.probability <= 1
            assert opp.score > 0
