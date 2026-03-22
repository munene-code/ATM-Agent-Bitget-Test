# SA-GAIP Execution Bot

Python execution layer for the Sovereign Absolute SA-GAIP Pine Script.
Receives trade signals from TradingView, validates them, and places orders on Bitget Futures.

## Architecture

```
TradingView SA-GAIP (Pine Script Section 27)
    ↓  JSON webhook
Railway FastAPI Bot  ←→  Telegram War Room (confirmations)
    ↓  Bitget API v2
Bitget USDT Futures (demo or live)
```

**The Pine Script is the brain.** It computes entry, SL, TP, size, and score.
The Python bot is a thin executor — it receives fully-formed signals and places orders.

## Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, webhook endpoint, orchestration |
| `bitget_client.py` | Bitget API v2 auth and order placement |
| `risk_manager.py` | Signal validation, dedup, open position tracking |
| `telegram_notifier.py` | Execution confirmations to War Room |
| `models.py` | Pydantic models matching Pine Script JSON output |
| `config.py` | All env vars in one place |

## Railway Deployment (Week 1)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "SA-GAIP bot initial"
git remote add origin https://github.com/YOUR_USERNAME/sa-gaip-bot.git
git push -u origin main
```

### 2. Create Railway project
1. Go to railway.app → New Project → Deploy from GitHub repo
2. Select your repo
3. Railway auto-detects Python and builds via Nixpacks

### 3. Set environment variables in Railway
In your Railway project → Variables, add every key from `.env.example`.
Start with `DEMO_MODE=true`.

### 4. Get your webhook URL
Railway gives you a public URL like:
```
https://sa-gaip-bot-production.up.railway.app
```

Your TradingView webhook URL is:
```
https://sa-gaip-bot-production.up.railway.app/webhook?secret=YOUR_WEBHOOK_SECRET
```

### 5. Configure TradingView alert
In SA-GAIP Pine Script:
- Set `enable_bitget = true` in inputs
- Create a TradingView alert on the indicator
- **Message**: `{{alert_message}}`
- **Webhook URL**: your Railway URL above
- **Trigger**: Bar close

## Pine Script Section 27 JSON format

The bot receives exactly this payload:
```json
{
  "action": "buy",
  "size": "0.0047",
  "symbol": "XAUUSDT",
  "price": "2341.55",
  "sl": "2336.20",
  "tp1": "2346.90",
  "id": "ATM-20260322-0815-BUY-01",
  "score": "9.0",
  "sync": "FULLY ALIGNED: BULLISH (4-LAYER)"
}
```

The bot computes `tp2` and `tp3` from the entry and risk distance.

## Risk Manager Rules

Signals are blocked if:
1. Duplicate trade ID (same signal fired twice)
2. Score below `MIN_SCORE_TO_EXECUTE` (default 4.0)
3. Counter-trend when `BLOCK_COUNTER_TREND=true`
4. Already have an open position on that symbol
5. SL is on wrong side of entry (Pine Script error protection)
6. Risk distance > 5% of price (abnormally wide stop)

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Railway health check |
| `/status` | GET | Positions, balance, recent executions |
| `/webhook?secret=X` | POST | Receives TradingView signals |
| `/close/{SYMBOL}?secret=X` | POST | Clear open position tracking after manual close |

## Going live

When ready to trade with real funds:
1. Set `DEMO_MODE=false` in Railway variables
2. The bot will send a `🔴 LIVE MODE` startup message to War Room
3. Redeploy or restart the Railway service

## TP Management (semi-auto)

The bot places entry + SL + TP1 automatically.
TP2 and TP3 are managed manually on Bitget, following Telegram alerts from the Pine Script.
When TP3 hits or SL hits, call `/close/SYMBOL?secret=X` to clear the bot's position tracking.
