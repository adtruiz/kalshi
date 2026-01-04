"""Spread analyzer for detecting arbitrage opportunities."""

from typing import List, Optional

from config.strategy_params import StrategyParams
from src.api.client import KalshiClientProtocol
from src.api.models import Market, OrderBook
from src.scanner.opportunity import SpreadOpportunity
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.analyzer")


class SpreadAnalyzer:
    """
    Analyzes markets to detect spread arbitrage opportunities.

    Uses the DankoWeb3 strategy:
    1. Look for spreads >= 3-5 cents
    2. Bet on the likely outcome side (midpoint > 50 = YES side likely)
    3. Expected profit from the spread when outcome resolves
    """

    def __init__(
        self,
        config: StrategyParams,
        rest_client: Optional[KalshiClientProtocol] = None,
    ) -> None:
        """
        Initialize the spread analyzer.

        Args:
            config: Strategy parameters for analysis
            rest_client: Optional API client for fetching orderbooks
        """
        self._config = config
        self._client = rest_client

    @property
    def config(self) -> StrategyParams:
        """Get the current strategy configuration."""
        return self._config

    def update_config(self, config: StrategyParams) -> None:
        """Update the strategy configuration."""
        self._config = config

    def determine_likely_side(self, orderbook: OrderBook) -> str:
        """
        Determine which side (YES or NO) is more likely to win.

        Uses the midpoint price as a probability estimate:
        - Midpoint > 50 cents means YES is more likely
        - Midpoint <= 50 cents means NO is more likely

        Args:
            orderbook: The market orderbook

        Returns:
            'yes' or 'no'
        """
        midpoint = orderbook.midpoint
        if midpoint is None:
            # Default to YES if we can't determine
            return "yes"

        return "yes" if midpoint > 50 else "no"

    def analyze_market(
        self,
        market: Market,
        orderbook: OrderBook,
    ) -> Optional[SpreadOpportunity]:
        """
        Analyze a market for spread arbitrage opportunity.

        Args:
            market: The market data
            orderbook: The market's orderbook

        Returns:
            SpreadOpportunity if one exists, None otherwise
        """
        # Get best bid/ask from orderbook
        yes_bid = orderbook.best_yes_bid
        yes_ask = orderbook.best_yes_ask

        if yes_bid is None or yes_ask is None:
            logger.debug(f"Skipping {market.ticker}: missing bid/ask data")
            return None

        spread = yes_ask - yes_bid

        # Check spread criteria
        if spread < self._config.min_spread_cents:
            logger.debug(
                f"Skipping {market.ticker}: spread {spread}c "
                f"< min {self._config.min_spread_cents}c"
            )
            return None

        if spread > self._config.max_spread_cents:
            logger.debug(
                f"Skipping {market.ticker}: spread {spread}c "
                f"> max {self._config.max_spread_cents}c"
            )
            return None

        # Determine likely side and probability
        likely_side = self.determine_likely_side(orderbook)
        midpoint = orderbook.midpoint or 50.0

        if likely_side == "yes":
            probability = midpoint / 100.0
        else:
            probability = 1.0 - (midpoint / 100.0)

        # Calculate spread percentage
        spread_pct = (spread / midpoint * 100) if midpoint > 0 else 0.0

        # Create opportunity
        opportunity = SpreadOpportunity(
            ticker=market.ticker,
            market_title=market.title,
            yes_bid=yes_bid,
            yes_ask=yes_ask,
            spread_cents=spread,
            spread_pct=spread_pct,
            likely_side=likely_side,
            probability=probability,
            volume_24h=market.volume_24h,
            liquidity=market.liquidity,
            expiration=market.expiration_time,
            expected_profit=0.0,  # Will be calculated
            score=0.0,  # Will be calculated
        )

        # Calculate expected profit and score
        opportunity.expected_profit = self._calculate_expected_profit(opportunity)
        opportunity.score = self.calculate_score(opportunity)

        logger.info(
            f"Found opportunity: {market.ticker} "
            f"spread={spread}c, side={likely_side}, score={opportunity.score:.2f}"
        )

        return opportunity

    def _calculate_expected_profit(self, opportunity: SpreadOpportunity) -> float:
        """
        Calculate expected profit per contract in cents.

        If we buy at the ask and the market resolves in our favor:
        - YES side: Buy YES at yes_ask, win 100 if YES wins
        - NO side: Buy NO at (100 - yes_bid), win 100 if NO wins

        Expected value = probability * payout - cost
        """
        if opportunity.likely_side == "yes":
            # Buy YES at the ask price
            cost = opportunity.yes_ask
            payout_if_win = 100
            expected_value = opportunity.probability * payout_if_win - cost
        else:
            # Buy NO at (100 - yes_bid) = no_ask
            cost = 100 - opportunity.yes_bid
            payout_if_win = 100
            expected_value = opportunity.probability * payout_if_win - cost

        return expected_value

    def calculate_score(self, opportunity: SpreadOpportunity) -> float:
        """
        Calculate a composite ranking score for the opportunity.

        Higher score = better opportunity

        Factors considered:
        1. Spread size (larger = better, within limits)
        2. Expected profit (higher = better)
        3. Probability strength (further from 50% = more confident)
        4. Liquidity (medium is optimal)
        5. Volume (higher = better)

        Args:
            opportunity: The opportunity to score

        Returns:
            Composite score (higher is better)
        """
        # Spread score: normalized to 0-10 range
        spread_score = min(opportunity.spread_cents / self._config.max_spread_cents, 1.0) * 10

        # Expected profit score: normalize expected profit
        profit_score = max(0, opportunity.expected_profit / 10)  # ~10 cents = score of 1

        # Probability confidence: how far from 50%
        confidence = abs(opportunity.probability - 0.5) * 2  # 0 to 1 scale
        confidence_score = confidence * 5

        # Liquidity score: penalize extremes, favor middle range
        mid_liquidity = (self._config.min_liquidity + self._config.max_liquidity) / 2
        liquidity_deviation = abs(opportunity.liquidity - mid_liquidity) / mid_liquidity
        liquidity_score = max(0, 5 - liquidity_deviation * 5)

        # Volume score: log scale, higher is better
        import math
        volume_score = min(math.log10(max(opportunity.volume_24h, 1)) / 4, 2.5)

        # Combine scores
        total_score = (
            spread_score * 0.25 +
            profit_score * 0.30 +
            confidence_score * 0.20 +
            liquidity_score * 0.15 +
            volume_score * 0.10
        )

        return round(total_score, 2)

    async def find_opportunities(
        self,
        markets: List[Market],
    ) -> List[SpreadOpportunity]:
        """
        Find all spread opportunities in the given markets.

        Args:
            markets: List of markets to analyze

        Returns:
            List of opportunities sorted by score (highest first)
        """
        if self._client is None:
            raise RuntimeError("REST client required to fetch orderbooks")

        opportunities: List[SpreadOpportunity] = []

        for market in markets:
            try:
                orderbook = await self._client.get_orderbook(market.ticker)
                opportunity = self.analyze_market(market, orderbook)

                if opportunity is not None:
                    opportunities.append(opportunity)

            except Exception as e:
                logger.error(f"Error analyzing {market.ticker}: {e}")
                continue

        # Sort by score descending
        opportunities.sort(key=lambda x: x.score, reverse=True)

        logger.info(f"Found {len(opportunities)} opportunities from {len(markets)} markets")

        return opportunities

    def analyze_with_orderbook(
        self,
        market: Market,
        orderbook: OrderBook,
    ) -> Optional[SpreadOpportunity]:
        """
        Analyze a market with a provided orderbook (for testing/external use).

        This is a convenience method that wraps analyze_market for external callers.

        Args:
            market: The market data
            orderbook: Pre-fetched orderbook

        Returns:
            SpreadOpportunity if one exists, None otherwise
        """
        return self.analyze_market(market, orderbook)
