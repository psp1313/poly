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
from typing import Optional

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

        # Real Data Components
        from market_finder import MarketFinder
        from websocket_manager import WebSocketManager
        
        self.market_finder = MarketFinder(self.client)
        self.ws_manager = WebSocketManager()
        
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
                api_passphrase=POLY_API_PASSPHRASE
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
        
        # Start WebSocket connection
        await self.ws_manager.connect()
        
        # Send startup notification
        await self.notifier.notify_startup()
        
        logger.info("Bot started - scanning for opportunities...")
        
        try:
            # Main loop
            while self.running:
                await self.scan_cycle()
                await asyncio.sleep(5)  # Scan every 5 seconds (faster with real data)
                
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
            
            # Get active market via Market Finder
            market_data = self._get_active_market()
            
            if not market_data:
                logger.debug("No active BTC market found")
                return
            
            market_id = market_data["market_id"]
            
            # Ensure we are subscribed to this market's tokens
            token_ids = [market_data["up_token_id"], market_data["down_token_id"]]
            if self.ws_manager.token_ids != token_ids:
                logger.info(f"Switching subscriptions to new market: {market_id}")
                await self.ws_manager.subscribe(token_ids)
                await asyncio.sleep(1) # Wait for book to populate
            
            # Get order book from WebSocket Manager
            order_book = await self._get_order_book(market_id, token_ids)
            
            if not order_book:
                return
            
            # Scan for opportunities
            # Note: We need start_price. Market Finder might need to scrape/infer it.
            # For now, approximate or assume placeholder until MarketFinder is robust.
            # Market Finder returns 'question' which might contain "$95000".
            # Let's extract it or use a fallback.
            start_price = self._extract_strike_price(market_data["question"])
            
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
    
    def _extract_strike_price(self, question: str) -> float:
        """Extract strike price from question string (e.g. 'Will BTC be > $95,000?')"""
        try:
            # Simple regex logic or string splitting
            # "Will Bitcoin be > $95,000 on ...?"
            import re
            match = re.search(r'\$([\d,]+)', question)
            if match:
                return float(match.group(1).replace(',', ''))
            return 100000.0 # Fallback safety
        except:
            return 100000.0

    def _get_active_market(self) -> Optional[dict]:
        """Get active market from MarketFinder"""
        return self.market_finder.find_active_btc_market()
    
    async def _get_order_book(self, market_id: str, token_ids: list) -> Optional[dict]:
        """Get combined order book from WebSocket Manager"""
        # We need to combine Up and Down token books into one structure for the engine
        up_book = self.ws_manager.get_order_book(token_ids[0])
        down_book = self.ws_manager.get_order_book(token_ids[1])
        
        if not up_book or not down_book:
            return None
            
        return {
            "up_asks": up_book["asks"],
            "up_bids": up_book["bids"],
            "down_asks": down_book["asks"],
            "down_bids": down_book["bids"]
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
