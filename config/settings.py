"""
Configuration settings for Polymarket Arbitrage Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Polymarket API
POLY_API_KEY = os.getenv("POLY_API_KEY")
POLY_API_SECRET = os.getenv("POLY_API_SECRET")
POLY_API_PASSPHRASE = os.getenv("POLY_API_PASSPHRASE")
POLY_PRIVATE_KEY = os.getenv("POLY_PRIVATE_KEY")
POLY_CHAIN_ID = int(os.getenv("POLY_CHAIN_ID", "137"))
POLY_SIG_TYPE = int(os.getenv("POLY_SIG_TYPE", "2"))
POLY_FUNDER_ADDRESS = os.getenv("POLY_FUNDER_ADDRESS")

# Trading Parameters
MAX_POSITION_SIZE_TESTING = float(os.getenv("MAX_POSITION_TESTING", "3.0"))  # $3 for testing
MAX_POSITION_SIZE_PROD = float(os.getenv("MAX_POSITION_PROD", "10.0"))  # $10 for production
MIN_PROFIT_THRESHOLD = float(os.getenv("MIN_PROFIT_THRESHOLD", "0.04"))  # 4% minimum
MAX_SLIPPAGE = float(os.getenv("MAX_SLIPPAGE", "0.025"))  # 2.5% max slippage
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", "5.0"))  # Stop if down $5/day

# Market Focus
TARGET_MARKET_PREFIX = "btc-updown-15m"  # Only trade BTC 15-min markets

# Telegram Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# WebSocket URLs
POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"

# Testing Mode
TESTING_MODE = os.getenv("TESTING_MODE", "True").lower() == "true"

def get_max_position_size():
    """Get max position size based on testing mode"""
    return MAX_POSITION_SIZE_TESTING if TESTING_MODE else MAX_POSITION_SIZE_PROD
