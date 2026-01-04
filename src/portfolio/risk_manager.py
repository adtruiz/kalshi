"""Risk management for the portfolio."""

from typing import Tuple

from config.strategy_params import StrategyParams
from src.api import MockRestClient, SpreadOpportunity
from src.models import TrackedPosition
from src.portfolio.position_tracker import PositionTracker
from src.utils.logger import get_logger

logger = get_logger("kalshi_bot.risk_manager")


class RiskManager:
    """
    Manages risk limits and position sizing.

    Enforces risk rules including:
    - Maximum position size
    - Maximum concurrent positions
    - Daily loss limits
    - Per-trade risk limits
    """

    def __init__(
        self,
        rest_client: MockRestClient,
        position_tracker: PositionTracker,
        params: StrategyParams,
    ):
        self._rest_client = rest_client
        self._position_tracker = position_tracker
        self._params = params
        self._initial_balance: int = 0
        self._trading_halted: bool = False
        self._halt_reason: str = ""

    async def initialize(self):
        """Initialize risk manager with current balance."""
        balance = await self._rest_client.get_balance()
        self._initial_balance = balance.balance
        logger.info(f"Risk manager initialized. Balance: ${balance.balance / 100:.2f}")

    async def can_open_position(
        self,
        opportunity: SpreadOpportunity,
        size: int,
    ) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            opportunity: The trading opportunity
            size: Proposed position size

        Returns:
            Tuple of (allowed, reason)
        """
        # Check if trading is halted
        if self._trading_halted:
            return False, f"Trading halted: {self._halt_reason}"

        # Check max concurrent positions
        open_positions = self._position_tracker.get_position_count()
        if open_positions >= self._params.max_concurrent_positions:
            return False, f"Max concurrent positions ({self._params.max_concurrent_positions}) reached"

        # Check if already have position in this ticker
        existing = self._position_tracker.get_position(opportunity.ticker)
        if existing and existing.quantity > 0:
            return False, f"Already have position in {opportunity.ticker}"

        # Check position size limit
        if size > self._params.max_position_size:
            return False, f"Size {size} exceeds max position size ({self._params.max_position_size})"

        # Check available balance
        balance = await self._rest_client.get_balance()
        cost = opportunity.bid_price * size
        if cost > balance.available_balance:
            return False, f"Insufficient balance. Need ${cost/100:.2f}, have ${balance.available_balance/100:.2f}"

        # Check daily loss limit
        daily_pnl = self._position_tracker.get_daily_pnl()
        daily_loss_limit = int(self._initial_balance * self._params.daily_loss_limit_pct)

        if daily_pnl < 0 and abs(daily_pnl) >= daily_loss_limit:
            self._trading_halted = True
            self._halt_reason = f"Daily loss limit (${daily_loss_limit/100:.2f}) exceeded"
            return False, self._halt_reason

        return True, "OK"

    def calculate_position_size(
        self,
        opportunity: SpreadOpportunity,
        balance: int,
    ) -> int:
        """
        Calculate optimal position size for an opportunity.

        Uses risk-based position sizing:
        - Risk per trade is a % of balance
        - Position size = risk amount / potential loss per contract

        Args:
            opportunity: The trading opportunity
            balance: Available balance in cents

        Returns:
            Recommended position size (number of contracts)
        """
        # Risk amount is a percentage of balance
        risk_amount = int(balance * self._params.risk_per_trade_pct)

        # Maximum loss per contract is the entry price (worst case: market goes to 0)
        max_loss_per_contract = opportunity.bid_price

        if max_loss_per_contract <= 0:
            return 0

        # Calculate size based on risk
        risk_based_size = risk_amount // max_loss_per_contract

        # Also consider expected profit-based sizing
        # More aggressive when spread is wider
        profit_per_contract = opportunity.spread_cents - 2  # Account for fees
        if profit_per_contract > 0:
            # Allocate more when expected return is higher
            profit_factor = min(2.0, 1.0 + (profit_per_contract / 10))
            risk_based_size = int(risk_based_size * profit_factor)

        # Apply maximum position size limit
        size = min(risk_based_size, self._params.max_position_size)

        # Ensure we can afford it
        cost = opportunity.bid_price * size
        if cost > balance:
            size = balance // opportunity.bid_price

        logger.debug(
            f"Position size calculation: risk_amount={risk_amount}c, "
            f"max_loss={max_loss_per_contract}c, size={size}"
        )

        return max(1, size)  # At least 1 contract

    def should_exit_position(
        self,
        position: TrackedPosition,
    ) -> Tuple[bool, str]:
        """
        Check if a position should be exited.

        Args:
            position: The position to evaluate

        Returns:
            Tuple of (should_exit, reason)
        """
        # Check stop loss
        if position.cost_basis > 0:
            loss_pct = abs(position.total_pnl) / position.cost_basis
            if position.total_pnl < 0 and loss_pct >= self._params.position_stop_loss_pct:
                return True, f"Stop loss triggered ({loss_pct:.1%} loss)"

        return False, ""

    def reset_daily_limits(self):
        """Reset daily loss tracking (call at start of new trading day)."""
        self._trading_halted = False
        self._halt_reason = ""
        logger.info("Daily risk limits reset")

    def halt_trading(self, reason: str):
        """Manually halt trading."""
        self._trading_halted = True
        self._halt_reason = reason
        logger.warning(f"Trading halted: {reason}")

    def resume_trading(self):
        """Resume trading after manual halt."""
        if not self._halt_reason.startswith("Daily loss"):
            self._trading_halted = False
            self._halt_reason = ""
            logger.info("Trading resumed")
        else:
            logger.warning("Cannot resume trading: daily loss limit still in effect")

    @property
    def is_trading_halted(self) -> bool:
        """Check if trading is currently halted."""
        return self._trading_halted

    @property
    def halt_reason(self) -> str:
        """Get the reason trading was halted."""
        return self._halt_reason
