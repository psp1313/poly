# Polymarket Arbitrage Bot

## Professional-grade arbitrage trading system for BTC 15-minute binary markets

Based on the $40M strategy: mathematical arbitrage with <5ms latency.

### Features
- ✅ WebSocket feeds (Polymarket CLOB + Binance BTC price)
- ✅ Sum-to-one arbitrage detection
- ✅ Momentum misalignment trading
- ✅ VWAP-based slippage protection
- ✅ Telegram notifications
- ✅ 4% minimum profit threshold

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env
cp .env.example .env
# Add your credentials

# Run locally
python src/main.py

# Deploy to Railway
railway up
```

### Project Structure
```
polymarket_arbitrage/
├── src/
│   ├── main.py              # Entry point
│   ├── websocket_feed.py    # Real-time market data
│   ├── arbitrage_engine.py  # Opportunity detection
│   ├── execution_manager.py # Order execution
│   └── telegram_notifier.py # Alerts
├── config/
│   └── settings.py          # Configuration
├── logs/                    # Trade logs
├── Dockerfile              # For Railway
├── railway.toml            # Railway config
└── requirements.txt
```

### Risk Management
- **Testing**: $3 max position
- **Production**: $10 max position
- **Profit Target**: 4%+ guaranteed edge
- **Daily Stop**: Pause if down $5

### Deployment
Runs 24/7 on Railway (free tier)
