# Polymarket Arbitrage Bot - Setup Guide

## Step 1: Telegram Bot Setup

### Create Your Bot
1. Open Telegram app
2. Search for **@BotFather**
3. Send: `/newbot`
4. Name: `Polymarket Arbitrage Bot`
5. Username: `your_username_arb_bot` (must end in 'bot')
6. **SAVE THE TOKEN** (looks like `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Get Your Chat ID
1. Search for **@userinfobot**
2. Send any message
3. **SAVE YOUR CHAT ID** (looks like `123456789`)

## Step 2: Configure Environment

```bash
cd /Users/tzankov/.gemini/antigravity/scratch/polymarket_arbitrage

# Copy template
cp .env.example .env

# Edit .env
nano .env
```

Add your credentials:
```
# Copy from your existing bot (polymarket_fetcher/.env)
POLY_API_KEY=your_key
POLY_API_SECRET=your_secret  
POLY_API_PASSPHRASE=your_passphrase
POLY_PRIVATE_KEY=your_private_key
POLY_FUNDER_ADDRESS=your_address

# Add Telegram (from steps above)
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
```

## Step 3: Install Dependencies

```bash
python3 -m pip install -r requirements.txt
```

## Step 4: Test Telegram

```bash
python3 src/telegram_notifier.py
```

You should get a test message in Telegram! ✅

## Step 5: Test WebSocket Feeds

```bash
python3 src/websocket_feed.py
```

You should see:
```
Connected to Polymarket WebSocket
Connected to Binance WebSocket
Got data update:
  BTC Price: $76,500.00
  Momentum (5s): +0.15%
```

## Next Steps

Once basic tests pass:
1. Build arbitrage engine (Phase 2)
2. Build execution manager (Phase 3)
3. Deploy to Railway (Phase 4)

## Troubleshooting

**Telegram not working?**
- Check bot token is correct
- Make sure you sent /start to your bot first

**WebSocket errors?**
- Check internet connection
- Polymarket WS might need authentication (TBD)

**Missing dependencies?**
```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt --force-reinstall
```
