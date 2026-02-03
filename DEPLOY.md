# Railway Deployment Guide

## Step 1: Get New Telegram Bot Token

**IMPORTANT:** Your old token was exposed. Create a new one:

1. Open Telegram → `@BotFather`
2. Send: `/revoke` → select your bot → confirm
3. Send: `/newtoken` → select your bot
4. Copy the NEW token

## Step 2: Deploy to Railway

1. Go to: https://railway.app
2. New Project → Deploy from GitHub
3. Select: `psp1313/poly`
4. Add Variables (see below)
5. Deploy!

## Step 3: Environment Variables

**Add these in Railway Variables tab:**

```
POLY_API_KEY=<your_key_here>
POLY_API_SECRET=<your_secret_here>
POLY_API_PASSPHRASE=<your_passphrase_here>
POLY_PRIVATE_KEY=<your_private_key_here>
POLY_CHAIN_ID=137
POLY_SIG_TYPE=2
POLY_FUNDER_ADDRESS=<your_address_here>

TESTING_MODE=True
MAX_POSITION_TESTING=3.0
MIN_PROFIT_THRESHOLD=0.04
MAX_SLIPPAGE=0.025
DAILY_LOSS_LIMIT=5.0

TELEGRAM_BOT_TOKEN=<YOUR_NEW_TOKEN_HERE>
TELEGRAM_CHAT_ID=6787842336
```

**DO NOT commit actual credentials to Git!**

## What the Bot Does

- Scans every 10 seconds for 4%+ arbitrage
- Max $3 position (testing mode)
- Telegram notifications for all activity
- Stops if daily loss hits $5

## Monitoring

- Check Railway logs for activity
- Telegram will send all trade updates
- Bot runs 24/7 automatically
