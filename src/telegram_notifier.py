"""
Telegram Notifier for Polymarket Arbitrage Bot

Sends real-time trade alerts and daily summaries
"""
import aiohttp
import logging
from typing import Dict, Optional
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send notifications via Telegram"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured - notifications disabled")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"Telegram notifications enabled for chat {self.chat_id}")
    
    async def send_message(self, message: str):
        """Send a text message to Telegram"""
        if not self.enabled:
            return
        
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.debug("Telegram message sent successfully")
                    else:
                        logger.error(f"Telegram error: {response.status}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    async def notify_startup(self):
        """Notify bot has started"""
        message = "🤖 *Polymarket Arbitrage Bot Started*\n\n"
        message += "✅ WebSocket feeds connected\n"
        message += "✅ Monitoring btc-updown-15m markets\n"
        message += "✅ Min profit: 4%\n"
        message += "✅ Max position: $3 (testing mode)\n"
        await self.send_message(message)
    
    async def notify_opportunity(self, opportunity: Dict):
        """Notify arbitrage opportunity detected"""
        message = f"🔍 *Opportunity Detected!*\n\n"
        
        # Sanitize to avoid Markdown errors
        opp_type = str(opportunity.get('type', 'unknown')).replace('_', '-')
        mkt_id = str(opportunity.get('market_id', 'unknown')).replace('_', '-')
        
        message += f"Type: {opp_type}\n"
        message += f"Profit: {opportunity.get('profit_pct', 0)*100:.2f}%\n"
        message += f"Market: {mkt_id}\n"
        await self.send_message(message)
    
    async def notify_trade_entry(self, trade: Dict):
        """Notify trade execution"""
        message = f"📈 *TRADE ENTRY*\n\n"
        
        trade_type = trade.get('type', 'unknown')
        if trade_type == 'sum_arbitrage':
            message += f"Strategy: Sum-to-One Arbitrage\n"
            message += f"Up: {trade.get('up_size', 0):.2f} shares @ ${trade.get('up_price', 0):.3f}\n"
            message += f"Down: {trade.get('down_size', 0):.2f} shares @ ${trade.get('down_price', 0):.3f}\n"
            message += f"Total Cost: ${trade.get('total_cost', 0):.2f}\n"
            message += f"Expected Profit: ${trade.get('expected_profit', 0):.2f} ({trade.get('profit_pct', 0)*100:.1f}%)\n"
        else:
            message += f"Strategy: {trade_type}\n"
            message += f"Side: {trade.get('side', 'unknown')}\n"
            message += f"Size: {trade.get('size', 0):.2f} shares\n"
            message += f"Entry: ${trade.get('entry_price', 0):.3f}\n"
            message += f"Target: ${trade.get('target_price', 0):.3f}\n"
        
        message += f"\nMarket: `{trade.get('market_id', 'unknown')}`\n"
        message += f"Time: {trade.get('timestamp', 'unknown')}"
        
        await self.send_message(message)
    
    async def notify_trade_exit(self, trade: Dict):
        """Notify trade exit"""
        profit = trade.get('profit', 0)
        emoji = "💰" if profit > 0 else "❌"
        
        message = f"{emoji} *TRADE EXIT*\n\n"
        message += f"Profit/Loss: ${profit:.2f}\n"
        message += f"Return: {trade.get('return_pct', 0)*100:.1f}%\n"
        message += f"Duration: {trade.get('duration_seconds', 0):.0f}s\n"
        message += f"Market: `{trade.get('market_id', 'unknown')}`"
        
        await self.send_message(message)
    
    async def notify_error(self, error: str):
        """Notify error"""
        # Sanitize error text
        safe_error = str(error).replace('_', '-')
        message = f"⚠️ *ERROR*\n\n{safe_error}"
        await self.send_message(message)
    
    async def notify_daily_summary(self, summary: Dict):
        """Send daily P&L summary"""
        message = f"📊 *Daily Summary*\n\n"
        message += f"Total Trades: {summary.get('total_trades', 0)}\n"
        message += f"Winners: {summary.get('winners', 0)}\n"
        message += f"Losers: {summary.get('losers', 0)}\n"
        message += f"Win Rate: {summary.get('win_rate', 0)*100:.1f}%\n"
        message += f"\n"
        message += f"Gross Profit: ${summary.get('gross_profit', 0):.2f}\n"
        message += f"Gross Loss: ${summary.get('gross_loss', 0):.2f}\n"
        message += f"Net P&L: ${summary.get('net_pnl', 0):.2f}\n"
        message += f"\n"
        message += f"Avg Profit/Trade: ${summary.get('avg_profit', 0):.2f}\n"
        message += f"Best Trade: ${summary.get('best_trade', 0):.2f}\n"
        message += f"Worst Trade: ${summary.get('worst_trade', 0):.2f}\n"
        
        await self.send_message(message)
    
    async def notify_shutdown(self, reason: str = "User stopped"):
        """Notify bot shutdown"""
        message = f"🛑 *Bot Stopped*\n\n"
        message += f"Reason: {reason}"
        await self.send_message(message)


# Test function
async def test_telegram():
    """Test Telegram notifications"""
    notifier = TelegramNotifier()
    
    if not notifier.enabled:
        print("Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return
    
    print("Sending test message...")
    await notifier.send_message("🧪 Test message from Polymarket Arbitrage Bot!")
    print("Check your Telegram!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_telegram())
