"""Market scanner for discovering tradeable Kalshi markets."""

from datetime import datetime
from typing import List, Optional

from config.strategy_params import StrategyParams
from src.api.client import KalshiClientProtocol
from src.api.models import Market
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.scanner")


class MarketScanner:
    """
    Scans Kalshi markets to find candidates for spread arbitrage.

    Applies filtering criteria based on strategy parameters:
    - Market must be active
    - Sufficient time until expiration
    - Adequate trading volume
    - Liquidity within acceptable range (not too high, not too low)
    """

    def __init__(
        self,
        rest_client: KalshiClientProtocol,
        config: StrategyParams,
    ) -> None:
        """
        Initialize the market scanner.

        Args:
            rest_client: Kalshi API client for fetching market data
            config: Strategy parameters for filtering
        """
        self._client = rest_client
        self._config = config

    @property
    def config(self) -> StrategyParams:
        """Get the current strategy configuration."""
        return self._config

    def update_config(self, config: StrategyParams) -> None:
        """Update the strategy configuration."""
        self._config = config

    async def scan_markets(
        self,
        category: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[Market]:
        """
        Scan for active markets matching basic criteria.

        Filters applied:
        - Market status must be 'active'
        - Days to expiration >= min_days_to_expiration
        - 24h volume >= min_volume_24h

        Args:
            category: Optional category filter
            reference_time: Reference time for expiration calculation (defaults to now)

        Returns:
            List of markets passing initial filters
        """
        ref_time = reference_time or datetime.utcnow()

        logger.info("Starting market scan...")

        # Fetch all active markets
        markets = await self._client.get_all_markets(status="active", category=category)

        logger.info(f"Fetched {len(markets)} active markets")

        filtered: List[Market] = []

        for market in markets:
            # Check expiration
            days_to_exp = market.days_to_expiration(ref_time)
            if days_to_exp < self._config.min_days_to_expiration:
                logger.debug(
                    f"Skipping {market.ticker}: expires in {days_to_exp:.1f} days "
                    f"(min: {self._config.min_days_to_expiration})"
                )
                continue

            # Check volume
            if market.volume_24h < self._config.min_volume_24h:
                logger.debug(
                    f"Skipping {market.ticker}: volume {market.volume_24h} "
                    f"(min: {self._config.min_volume_24h})"
                )
                continue

            filtered.append(market)

        logger.info(
            f"After expiration/volume filters: {len(filtered)} markets remain"
        )

        return filtered

    def filter_by_liquidity(self, markets: List[Market]) -> List[Market]:
        """
        Filter markets by liquidity range.

        Markets with liquidity that is too low may be hard to enter/exit.
        Markets with liquidity that is too high tend to have tight spreads
        (efficient markets) with no arbitrage opportunity.

        Args:
            markets: List of markets to filter

        Returns:
            Markets with liquidity in acceptable range
        """
        filtered: List[Market] = []

        for market in markets:
            if market.liquidity < self._config.min_liquidity:
                logger.debug(
                    f"Skipping {market.ticker}: liquidity {market.liquidity} "
                    f"below minimum {self._config.min_liquidity}"
                )
                continue

            if market.liquidity > self._config.max_liquidity:
                logger.debug(
                    f"Skipping {market.ticker}: liquidity {market.liquidity} "
                    f"exceeds maximum {self._config.max_liquidity}"
                )
                continue

            filtered.append(market)

        logger.info(
            f"After liquidity filter: {len(filtered)} markets remain "
            f"(range: {self._config.min_liquidity}-{self._config.max_liquidity})"
        )

        return filtered

    async def get_tradeable_markets(
        self,
        category: Optional[str] = None,
        reference_time: Optional[datetime] = None,
    ) -> List[Market]:
        """
        Get all markets that pass all filters.

        Convenience method that combines scan_markets and filter_by_liquidity.

        Args:
            category: Optional category filter
            reference_time: Reference time for expiration calculation

        Returns:
            List of tradeable markets
        """
        markets = await self.scan_markets(category, reference_time)
        return self.filter_by_liquidity(markets)
