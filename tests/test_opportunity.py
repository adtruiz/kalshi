"""Tests for SpreadOpportunity dataclass."""

from datetime import datetime, timedelta

import pytest

from src.scanner.opportunity import SpreadOpportunity


class TestSpreadOpportunity:
    """Tests for SpreadOpportunity dataclass."""

    def test_valid_opportunity_creation(self):
        """Test creating a valid spread opportunity."""
        expiration = datetime.utcnow() + timedelta(days=5)

        opportunity = SpreadOpportunity(
            ticker="KXBTC-24JAN15-T50000",
            market_title="Will BTC exceed $50,000?",
            yes_bid=45,
            yes_ask=52,
            spread_cents=7,
            spread_pct=14.4,
            likely_side="yes",
            probability=0.65,
            volume_24h=500,
            liquidity=5000,
            expiration=expiration,
            expected_profit=8.5,
            score=3.75,
        )

        assert opportunity.ticker == "KXBTC-24JAN15-T50000"
        assert opportunity.yes_bid == 45
        assert opportunity.yes_ask == 52
        assert opportunity.spread_cents == 7
        assert opportunity.likely_side == "yes"
        assert opportunity.probability == 0.65

    def test_midpoint_calculation(self):
        """Test midpoint property calculation."""
        opportunity = SpreadOpportunity(
            ticker="TEST",
            market_title="Test",
            yes_bid=40,
            yes_ask=60,
            spread_cents=20,
            spread_pct=40.0,
            likely_side="yes",
            probability=0.5,
            volume_24h=100,
            liquidity=1000,
            expiration=datetime.utcnow(),
        )

        assert opportunity.midpoint == 50.0

    def test_no_bid_ask_properties(self):
        """Test implied NO bid/ask calculations."""
        opportunity = SpreadOpportunity(
            ticker="TEST",
            market_title="Test",
            yes_bid=45,
            yes_ask=55,
            spread_cents=10,
            spread_pct=20.0,
            likely_side="yes",
            probability=0.5,
            volume_24h=100,
            liquidity=1000,
            expiration=datetime.utcnow(),
        )

        # NO bid = 100 - YES ask
        assert opportunity.no_bid == 45  # 100 - 55
        # NO ask = 100 - YES bid
        assert opportunity.no_ask == 55  # 100 - 45

    def test_invalid_yes_bid_raises_error(self):
        """Test that invalid yes_bid raises ValueError."""
        with pytest.raises(ValueError, match="yes_bid must be 0-100"):
            SpreadOpportunity(
                ticker="TEST",
                market_title="Test",
                yes_bid=101,  # Invalid
                yes_ask=55,
                spread_cents=10,
                spread_pct=20.0,
                likely_side="yes",
                probability=0.5,
                volume_24h=100,
                liquidity=1000,
                expiration=datetime.utcnow(),
            )

    def test_invalid_yes_ask_raises_error(self):
        """Test that invalid yes_ask raises ValueError."""
        with pytest.raises(ValueError, match="yes_ask must be 0-100"):
            SpreadOpportunity(
                ticker="TEST",
                market_title="Test",
                yes_bid=45,
                yes_ask=-5,  # Invalid
                spread_cents=10,
                spread_pct=20.0,
                likely_side="yes",
                probability=0.5,
                volume_24h=100,
                liquidity=1000,
                expiration=datetime.utcnow(),
            )

    def test_bid_exceeds_ask_raises_error(self):
        """Test that bid > ask raises ValueError."""
        with pytest.raises(ValueError, match="cannot exceed"):
            SpreadOpportunity(
                ticker="TEST",
                market_title="Test",
                yes_bid=60,  # Bid higher than ask
                yes_ask=50,
                spread_cents=10,
                spread_pct=20.0,
                likely_side="yes",
                probability=0.5,
                volume_24h=100,
                liquidity=1000,
                expiration=datetime.utcnow(),
            )

    def test_invalid_likely_side_raises_error(self):
        """Test that invalid likely_side raises ValueError."""
        with pytest.raises(ValueError, match="likely_side must be"):
            SpreadOpportunity(
                ticker="TEST",
                market_title="Test",
                yes_bid=45,
                yes_ask=55,
                spread_cents=10,
                spread_pct=20.0,
                likely_side="maybe",  # Invalid
                probability=0.5,
                volume_24h=100,
                liquidity=1000,
                expiration=datetime.utcnow(),
            )

    def test_invalid_probability_raises_error(self):
        """Test that invalid probability raises ValueError."""
        with pytest.raises(ValueError, match="probability must be 0-1"):
            SpreadOpportunity(
                ticker="TEST",
                market_title="Test",
                yes_bid=45,
                yes_ask=55,
                spread_cents=10,
                spread_pct=20.0,
                likely_side="yes",
                probability=1.5,  # Invalid
                volume_24h=100,
                liquidity=1000,
                expiration=datetime.utcnow(),
            )

    def test_to_dict(self):
        """Test conversion to dictionary."""
        expiration = datetime(2024, 1, 15, 12, 0, 0)

        opportunity = SpreadOpportunity(
            ticker="TEST",
            market_title="Test Market",
            yes_bid=45,
            yes_ask=52,
            spread_cents=7,
            spread_pct=14.4,
            likely_side="yes",
            probability=0.65,
            volume_24h=500,
            liquidity=5000,
            expiration=expiration,
            expected_profit=8.5,
            score=3.75,
        )

        result = opportunity.to_dict()

        assert result["ticker"] == "TEST"
        assert result["yes_bid"] == 45
        assert result["yes_ask"] == 52
        assert result["expiration"] == "2024-01-15T12:00:00"
        assert result["score"] == 3.75

    def test_repr(self):
        """Test string representation."""
        opportunity = SpreadOpportunity(
            ticker="KXBTC",
            market_title="Test",
            yes_bid=45,
            yes_ask=52,
            spread_cents=7,
            spread_pct=14.4,
            likely_side="yes",
            probability=0.65,
            volume_24h=100,
            liquidity=1000,
            expiration=datetime.utcnow(),
            score=3.75,
        )

        repr_str = repr(opportunity)
        assert "KXBTC" in repr_str
        assert "spread=7c" in repr_str
        assert "side=yes" in repr_str
        assert "65.0%" in repr_str

    def test_default_values(self):
        """Test default values for expected_profit and score."""
        opportunity = SpreadOpportunity(
            ticker="TEST",
            market_title="Test",
            yes_bid=45,
            yes_ask=55,
            spread_cents=10,
            spread_pct=20.0,
            likely_side="yes",
            probability=0.5,
            volume_24h=100,
            liquidity=1000,
            expiration=datetime.utcnow(),
        )

        assert opportunity.expected_profit == 0.0
        assert opportunity.score == 0.0

    def test_edge_case_zero_bid(self):
        """Test edge case with yes_bid at 0."""
        opportunity = SpreadOpportunity(
            ticker="TEST",
            market_title="Test",
            yes_bid=0,
            yes_ask=5,
            spread_cents=5,
            spread_pct=200.0,
            likely_side="no",
            probability=0.975,
            volume_24h=100,
            liquidity=1000,
            expiration=datetime.utcnow(),
        )

        assert opportunity.yes_bid == 0
        assert opportunity.no_ask == 100  # 100 - 0

    def test_edge_case_high_ask(self):
        """Test edge case with yes_ask at 100."""
        opportunity = SpreadOpportunity(
            ticker="TEST",
            market_title="Test",
            yes_bid=95,
            yes_ask=100,
            spread_cents=5,
            spread_pct=5.1,
            likely_side="yes",
            probability=0.975,
            volume_24h=100,
            liquidity=1000,
            expiration=datetime.utcnow(),
        )

        assert opportunity.yes_ask == 100
        assert opportunity.no_bid == 0  # 100 - 100
