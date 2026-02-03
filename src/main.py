"""
Main Bot - Polymarket Arbitrage Trader

Integrates all components:
- WebSocket feeds (Polymarket + Chainlink)
- Arbitrage detection engine
- Order execution manager
- Telegram notifications

Runs continuously, scanning for arbitrage opportunities.
"""
import asyncio
import logging
import sys
import os
import signal
import datetime

# Add parent directory (project root) to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE,
    POLY_PRIVATE_KEY, POLY_CHAIN_ID, POLY_SIG_TYPE, POLY_FUNDER_ADDRESS,
    get_max_position_size, MIN_PROFIT_THRESHOLD, DAILY_LOSS_LIMIT,
    TESTING_MODE
)
from telegram_notifier import TelegramNotifier
from chainlink_oracle import PriceOracle
from arbitrage_engine import ArbitrageEngine
from execution_manager import ExecutionManager

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import POLYGON

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ArbitrageBot:
    """Main arbitrage trading bot"""
    
    def __init__(self):
        self.running = False
        self.daily_pnl = 0.0
        
        # Initialize components
        logger.info("=== POLYMARKET ARBITRAGE BOT ===")
        logger.info(f"Mode: {'TESTING' if TESTING_MODE else 'PRODUCTION'}")
        logger.info(f"Max Position: ${get_max_position_size()}")
        logger.info(f"Min Profit: {MIN_PROFIT_THRESHOLD*100}%")
        
        # Telegram notifier
        self.notifier = TelegramNotifier()
        
        # Polymarket client
        self.client = self._init_client()
        
        # Price oracle (Chainlink + Binance)
        self.oracle = PriceOracle()
        
        # Arbitrage engine
        self.arb_engine = ArbitrageEngine(
            min_profit_pct=MIN_PROFIT_THRESHOLD,
            max_slippage=0.025
        )
        
        # Execution manager
        self.exec_manager = ExecutionManager(self.client)
        
        logger.info("All components initialized")
    
    def _init_client(self) -> ClobClient:
        """Initialize Polymarket CLOB client"""
        try:
            # Create API credentials
            creds = ApiCreds(
                api_key=POLY_API_KEY,
                api_secret=POLY_API_SECRET,
                api_passphrase=POLY_API_PASSPHRASE,
                private_key=POLY_PRIVATE_KEY
            )
            
            # Initialize client
            client = ClobClient(
                host="https://clob.polymarket.com",
                chain_id=POLY_CHAIN_ID,
                key=POLY_PRIVATE_KEY,
                creds=creds,
                signature_type=POLY_SIG_TYPE,
                funder=POLY_FUNDER_ADDRESS
            )
            
            logger.info("Polymarket client initialized")
            return client
            
        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}")
            raise
    
    async def start(self):
        """Start the bot"""
        self.running = True
        
        # Send startup notification
        await self.notifier.notify_startup()
        
        logger.info("Bot started - scanning for opportunities...")
        
        try:
            # Main loop
            while self.running:
                await self.scan_cycle()
                await asyncio.sleep(10)  # Scan every 10 seconds
                
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        finally:
            await self.stop()
    
    async def scan_cycle(self):
        """Single scan cycle"""
        try:
            # Get current BTC price from Chainlink
            prices = await self.oracle.get_btc_price()
            chainlink_btc = prices.get("chainlink")
            
            if not chainlink_btc:
                logger.warning("Failed to get Chainlink BTC price")
                return
            
            # Get active market
            market_id, start_price = self._get_active_market()
            
            if not market_id:
                logger.debug("No active market found")
                return
            
            # Get order book (placeholder - needs WebSocket integration)
            order_book = await self._get_order_book(market_id)
            
            if not order_book:
                return
            
            # Scan for opportunities
            opportunities = self.arb_engine.scan_opportunities(
                order_book=order_book,
                chainlink_btc=chainlink_btc,
                market_start_price=start_price,
                max_position=get_max_position_size(),
                market_id=market_id
            )
            
            # Execute best opportunity
            if opportunities:
                best_opp = opportunities[0]
                logger.info(f"Opportunity found: {best_opp.type} - {best_opp.profit_pct*100:.2f}% profit")
                
                # Notify
                await self.notifier.notify_opportunity({
                    "type": best_opp.type,
                    "profit_pct": best_opp.profit_pct,
                    "market_id": market_id
                })
                
                # Execute
                await self._execute_opportunity(best_opp)
                
        except Exception as e:
            logger.error(f"Scan cycle error: {e}")
            await self.notifier.notify_error(str(e))
    
    def _get_active_market(self) -> tuple:
        """
        Get current active btc-updown-15m market
        
        Returns:
            (market_id, start_price) or (None, None)
        """
        try:
            # Calculate current 15-min interval
            now = datetime.datetime.now(datetime.timezone.utc)
            base = now.replace(second=0, microsecond=0)
            minutes_to_remove = base.minute % 15
            current_mark = base - datetime.timedelta(minutes=minutes_to_remove)
            ts = int(current_mark.timestamp())
            
            market_id = f"btc-updown-15m-{ts}"
            
            # For MVP, use cached Chainlink price as start
            # TODO: Query actual market start price from Polymarket
            start_price = 76500.0  # Placeholder
            
            return market_id, start_price
            
        except Exception as e:
            logger.error(f"Error getting active market: {e}")
            return None, None
    
    async def _get_order_book(self, market_id: str) -> dict:
        """
        Get order book for market
        
        For MVP, returns placeholder data.
        TODO: Integrate with WebSocket feed manager
        """
        # Placeholder
        return {
            "up_asks": [{"price": 0.50, "size": 100}],
            "up_bids": [{"price": 0.48, "size": 100}],
            "down_asks": [{"price": 0.45, "size": 100}],
            "down_bids": [{"price": 0.43, "size": 100}]
        }
    
    async def _execute_opportunity(self, opportunity):
        """Execute an arbitrage opportunity"""
        try:
            if opportunity.type == "sum_arbitrage":
                # Execute both sides
                success, message = await self.exec_manager.execute_sum_arbitrage(
                    market_id=opportunity.market_id,
                    up_token_id="placeholder_up",  # TODO: Get from market data
                    down_token_id="placeholder_down",
                    up_price=opportunity.up_price,
                    down_price=opportunity.down_price,
                    size=opportunity.up_size
                )
                
                if success:
                    await self.notifier.notify_trade_entry({
                        "type": "sum_arbitrage",
                        "up_size": opportunity.up_size,
                        "up_price": opportunity.up_price,
                        "down_size": opportunity.down_size,
                        "down_price": opportunity.down_price,
                        "total_cost": opportunity.total_cost,
                        "expected_profit": opportunity.expected_profit,
                        "profit_pct": opportunity.profit_pct,
                        "market_id": opportunity.market_id,
                        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                else:
                    await self.notifier.notify_error(f"Execution failed: {message}")
                    
        except Exception as e:
            logger.error(f"Execution error: {e}")
            await self.notifier.notify_error(str(e))
    
    async def stop(self):
        """Stop the bot"""
        self.running = False
        await self.notifier.notify_shutdown("User stopped bot")
        logger.info("Bot stopped")


async def main():
    """Main entry point"""
    bot = ArbitrageBot()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start bot
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
