#!/usr/bin/env python3
"""
Kalshi Spread Arbitrage Bot

Automated trading bot that captures bid-ask spreads on Kalshi prediction markets.
Strategy: Find markets with 3-5+ cent spreads, buy at bid on likely outcome, sell at ask.

Usage:
    python main.py scan          # Scan for opportunities
    python main.py trade         # Run automated trading (requires confirmation)
    python main.py status        # Show current positions and P&L
    python main.py test-auth     # Test API authentication
"""

import argparse
import asyncio
import sys
from datetime import datetime

from config.settings import Settings, get_settings, Environment
from config.strategy_params import StrategyParams, DEFAULT_STRATEGY
from src.utils.logger import setup_logger, get_logger
from src.auth.kalshi_auth import KalshiAuth
from src.api.rest_client import KalshiRestClient
from src.api.websocket_client import KalshiWebSocketClient
from src.api.rate_limiter import RateLimiter
from src.scanner.market_scanner import MarketScanner
from src.scanner.spread_analyzer import SpreadAnalyzer
from src.execution.order_manager import OrderManager
from src.execution.execution_engine import ExecutionEngine
from src.portfolio.position_tracker import PositionTracker
from src.portfolio.risk_manager import RiskManager


# Setup logging
logger = setup_logger("kalshi_bot", log_file="logs/trading.log", level="INFO")


class TradingBot:
    """Main trading bot orchestrator."""

    def __init__(self, settings: Settings, strategy: StrategyParams):
        self.settings = settings
        self.strategy = strategy
        self.auth = None
        self.rest_client = None
        self.ws_client = None
        self.scanner = None
        self.analyzer = None
        self.order_manager = None
        self.execution_engine = None
        self.position_tracker = None
        self.risk_manager = None

    async def initialize(self) -> bool:
        """Initialize all components."""
        try:
            logger.info(f"Initializing bot in {self.settings.environment.value} mode")
            logger.info(f"API URL: {self.settings.base_url}")

            # Initialize authentication
            self.auth = KalshiAuth(
                key_id=self.settings.kalshi_api_key,
                private_key_path=str(self.settings.private_key_path),
            )

            # Initialize rate limiter
            rate_limiter = RateLimiter(
                read_limit=self.settings.read_rate_limit,
                write_limit=self.settings.write_rate_limit,
            )

            # Initialize REST client
            self.rest_client = KalshiRestClient(
                auth=self.auth,
                base_url=self.settings.base_url,
                rate_limiter=rate_limiter,
            )

            # Initialize WebSocket client
            self.ws_client = KalshiWebSocketClient(
                auth=self.auth,
                ws_url=self.settings.ws_url,
            )

            # Initialize scanner components
            self.scanner = MarketScanner(
                client=self.rest_client,
                config=self.strategy,
            )
            self.analyzer = SpreadAnalyzer(config=self.strategy)

            # Initialize portfolio components
            self.position_tracker = PositionTracker(client=self.rest_client)
            self.risk_manager = RiskManager(
                client=self.rest_client,
                config=self.strategy,
            )

            # Initialize execution components
            self.order_manager = OrderManager(
                rest_client=self.rest_client,
                ws_client=self.ws_client,
            )
            self.execution_engine = ExecutionEngine(
                order_manager=self.order_manager,
                position_tracker=self.position_tracker,
                risk_manager=self.risk_manager,
                config=self.strategy,
            )

            logger.info("Bot initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            return False

    async def test_authentication(self) -> bool:
        """Test API authentication."""
        try:
            logger.info("Testing API authentication...")
            balance = await self.rest_client.get_balance()
            logger.info(f"Authentication successful! Balance: ${balance:.2f}")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    async def scan_opportunities(self) -> None:
        """Scan for spread opportunities."""
        logger.info("Scanning for spread opportunities...")

        try:
            # Get markets
            markets = await self.scanner.scan_markets()
            logger.info(f"Found {len(markets)} markets matching criteria")

            if not markets:
                logger.info("No markets found matching criteria")
                return

            # Analyze for opportunities
            opportunities = []
            for market in markets[:50]:  # Limit to first 50 to avoid rate limits
                try:
                    orderbook = await self.rest_client.get_orderbook(market.ticker)
                    opportunity = await self.analyzer.analyze_market(market, orderbook)
                    if opportunity:
                        opportunities.append(opportunity)
                except Exception as e:
                    logger.debug(f"Error analyzing {market.ticker}: {e}")

            # Sort by score
            opportunities.sort(key=lambda x: x.score, reverse=True)

            # Display results
            if opportunities:
                logger.info(f"\n{'='*80}")
                logger.info(f"Found {len(opportunities)} opportunities:")
                logger.info(f"{'='*80}")

                for i, opp in enumerate(opportunities[:10], 1):
                    logger.info(
                        f"{i}. {opp.ticker}\n"
                        f"   Title: {opp.market_title[:50]}...\n"
                        f"   Spread: {opp.spread_cents}¢ ({opp.spread_pct:.1%})\n"
                        f"   Side: {opp.likely_side.upper()} @ {opp.probability:.0%}\n"
                        f"   Expected profit: ${opp.expected_profit:.2f}\n"
                        f"   Score: {opp.score:.2f}\n"
                    )
            else:
                logger.info("No profitable opportunities found")

        except Exception as e:
            logger.error(f"Error scanning: {e}")

    async def run_trading(self, auto_confirm: bool = False) -> None:
        """Run automated trading."""
        if self.settings.environment == Environment.PRODUCTION and not auto_confirm:
            confirm = input(
                "\n⚠️  WARNING: You are about to trade with REAL MONEY!\n"
                "Type 'CONFIRM PRODUCTION' to proceed: "
            )
            if confirm != "CONFIRM PRODUCTION":
                logger.info("Trading cancelled")
                return

        logger.info("Starting automated trading...")
        logger.info(f"Strategy: min_spread={self.strategy.min_spread_cents}¢, "
                    f"max_positions={self.strategy.max_concurrent_positions}")

        try:
            while True:
                # Scan for opportunities
                markets = await self.scanner.scan_markets()

                for market in markets[:20]:
                    try:
                        orderbook = await self.rest_client.get_orderbook(market.ticker)
                        opportunity = await self.analyzer.analyze_market(market, orderbook)

                        if opportunity and opportunity.score > 0.5:
                            # Check risk
                            can_trade, reason = await self.risk_manager.can_open_position(
                                opportunity, self.strategy.max_position_size
                            )

                            if can_trade:
                                logger.info(f"Executing trade on {opportunity.ticker}")
                                result = await self.execution_engine.execute_spread_trade(
                                    opportunity
                                )
                                logger.info(f"Trade result: {result}")
                            else:
                                logger.debug(f"Skipping {opportunity.ticker}: {reason}")

                    except Exception as e:
                        logger.debug(f"Error processing {market.ticker}: {e}")

                # Wait before next scan
                logger.info(f"Waiting {self.strategy.scan_interval_seconds}s before next scan...")
                await asyncio.sleep(self.strategy.scan_interval_seconds)

        except KeyboardInterrupt:
            logger.info("Trading stopped by user")
        except Exception as e:
            logger.error(f"Trading error: {e}")

    async def show_status(self) -> None:
        """Show current positions and P&L."""
        try:
            logger.info("Fetching current status...")

            # Get balance
            balance = await self.rest_client.get_balance()
            logger.info(f"\nAccount Balance: ${balance:.2f}")

            # Get positions
            await self.position_tracker.sync_positions()
            positions = self.position_tracker.get_all_positions()

            if positions:
                logger.info(f"\nOpen Positions ({len(positions)}):")
                logger.info("-" * 60)
                for pos in positions:
                    logger.info(
                        f"  {pos.ticker}: {pos.quantity} {pos.side.upper()} @ ${pos.avg_entry_price:.2f}\n"
                        f"    Unrealized P&L: ${pos.unrealized_pnl:.2f}"
                    )

                total_pnl = self.position_tracker.calculate_total_pnl()
                logger.info(f"\nTotal Unrealized P&L: ${total_pnl:.2f}")
            else:
                logger.info("\nNo open positions")

        except Exception as e:
            logger.error(f"Error fetching status: {e}")

    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self.rest_client:
            await self.rest_client.close()
        if self.ws_client:
            await self.ws_client.disconnect()


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Kalshi Spread Arbitrage Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "command",
        choices=["scan", "trade", "status", "test-auth"],
        help="Command to run"
    )
    parser.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Skip confirmation prompts (dangerous!)"
    )

    args = parser.parse_args()

    # Load settings
    settings = get_settings()
    strategy = DEFAULT_STRATEGY

    # Print banner
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║           Kalshi Spread Arbitrage Bot v0.1.0                  ║
║                                                               ║
║  Environment: {settings.environment.value.upper():^10}                                  ║
║  API: {settings.base_url[:45]:^50}    ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    # Initialize bot
    bot = TradingBot(settings, strategy)

    if not await bot.initialize():
        logger.error("Failed to initialize bot")
        sys.exit(1)

    try:
        if args.command == "test-auth":
            success = await bot.test_authentication()
            sys.exit(0 if success else 1)

        elif args.command == "scan":
            await bot.scan_opportunities()

        elif args.command == "trade":
            await bot.run_trading(auto_confirm=args.auto_confirm)

        elif args.command == "status":
            await bot.show_status()

    finally:
        await bot.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
