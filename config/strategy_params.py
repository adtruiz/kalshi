"""Strategy parameters for spread arbitrage trading."""

from pydantic import BaseModel, Field


class StrategyParams(BaseModel):
    """Configuration parameters for the spread arbitrage strategy."""

    # Spread Detection
    min_spread_cents: int = Field(
        default=3,
        description="Minimum spread in cents to consider trading"
    )
    max_spread_cents: int = Field(
        default=15,
        description="Maximum spread in cents (filter out illiquid markets)"
    )

    # Market Filtering
    min_days_to_expiration: int = Field(
        default=3,
        description="Minimum days until market expiration"
    )
    min_liquidity: int = Field(
        default=1000,
        description="Minimum liquidity threshold"
    )
    max_liquidity: int = Field(
        default=100000,
        description="Maximum liquidity (avoid highly efficient markets)"
    )
    min_volume_24h: int = Field(
        default=100,
        description="Minimum 24-hour trading volume"
    )

    # Position Sizing
    max_position_size: int = Field(
        default=100,
        description="Maximum contracts per position"
    )
    max_concurrent_positions: int = Field(
        default=5,
        description="Maximum number of open positions"
    )
    risk_per_trade_pct: float = Field(
        default=0.02,
        description="Risk per trade as fraction of balance (2%)"
    )

    # Order Management
    order_timeout_seconds: int = Field(
        default=300,
        description="Timeout for order fills (5 minutes)"
    )
    partial_fill_threshold: float = Field(
        default=0.5,
        description="Cancel if less than this fraction filled after timeout"
    )

    # Risk Management
    daily_loss_limit_pct: float = Field(
        default=0.05,
        description="Stop trading if daily loss exceeds this (5%)"
    )
    position_stop_loss_pct: float = Field(
        default=0.10,
        description="Exit position if loss exceeds this (10%)"
    )

    # Scanning
    scan_interval_seconds: int = Field(
        default=30,
        description="How often to scan for opportunities"
    )


# Default strategy parameters
DEFAULT_STRATEGY = StrategyParams()
