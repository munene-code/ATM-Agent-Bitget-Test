"""
SA-GAIP Bot — Main Application
FastAPI webhook receiver. Receives signals from TradingView Section 27 JSON,
validates them, sets leverage, places the order on Bitget, and confirms via Telegram.

Deploy on Railway. Set all env vars in Railway dashboard.
TradingView webhook URL: https://your-app.railway.app/webhook?secret=YOUR_SECRET
"""
import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse

import bitget_client
import risk_manager
import telegram_notifier
from config import get_settings
from models import SignalPayload, ExecutionRecord

# ── Logging ───────────────────────────────────────────────────────────────────
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory execution log (resets on restart — fine for demo phase)
execution_log: list[ExecutionRecord] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("SA-GAIP Bot starting...")
    missing = settings.validate()
    demo = settings.DEMO_MODE
    mode_str = "DEMO (paper trading)" if demo else "LIVE — REAL FUNDS"
    logger.info(f"Mode: {mode_str}")
    if missing:
        logger.warning(f"Missing config: {missing}")
    await telegram_notifier.notify_startup(demo, missing)
    yield
    logger.info("SA-GAIP Bot shutting down.")


app = FastAPI(
    title="SA-GAIP Execution Bot",
    description="Receives TradingView signals, validates, executes on Bitget.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Railway health check endpoint."""
    return {
        "status": "ok",
        "demo_mode": settings.DEMO_MODE,
        "open_positions": risk_manager.get_open_symbols(),
        "executions_today": len(execution_log),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/status")
async def status():
    """Detailed status — open positions and recent executions."""
    positions = await bitget_client.get_open_positions()
    balance = await bitget_client.get_account_balance()
    return {
        "demo_mode": settings.DEMO_MODE,
        "balance": balance,
        "open_positions_bitget": positions,
        "open_positions_bot": risk_manager.get_open_symbols(),
        "recent_executions": [
            {
                "id": r.signal.id,
                "symbol": r.signal.symbol,
                "action": r.signal.action,
                "success": r.order_result.success,
                "executed_at": r.executed_at,
            }
            for r in execution_log[-10:]
        ],
    }


# ── Main webhook ──────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_signal(
    request: Request,
    secret: str = Query(default=""),
):
    """
    Receive JSON signal from TradingView Pine Script Section 27.

    TradingView alert webhook URL:
        https://your-app.railway.app/webhook?secret=YOUR_WEBHOOK_SECRET

    TradingView alert message:
        {{alert_message}}  ← the bg_json variable from Section 27

    Expected JSON:
        {"action":"buy","size":"0.0047","symbol":"XAUUSDT","price":"2341.55",
         "sl":"2336.20","tp1":"2346.90","id":"ATM-20260322-0815-BUY-01",
         "score":"9.0","sync":"FULLY ALIGNED: BULLISH (4-LAYER)"}
    """

    # 1. Validate webhook secret
    if settings.WEBHOOK_SECRET and secret != settings.WEBHOOK_SECRET:
        logger.warning(f"Unauthorized webhook attempt — bad secret")
        raise HTTPException(status_code=403, detail="Unauthorized")

    # 2. Parse body
    try:
        raw_body = await request.body()
        data = json.loads(raw_body)
    except Exception as e:
        logger.error(f"Failed to parse webhook body: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    logger.info(f"Webhook received: {data}")

    # 3. Validate signal model
    try:
        signal = SignalPayload(**data)
    except Exception as e:
        logger.error(f"Signal validation error: {e}")
        raise HTTPException(status_code=422, detail=f"Signal parse error: {e}")

    # 4. Risk checks
    try:
        risk_manager.validate(signal)
    except risk_manager.RiskBlock as rb:
        logger.warning(f"Risk block: {rb.reason}")
        await telegram_notifier.notify_risk_block(signal, rb.reason)
        return JSONResponse(
            status_code=200,
            content={"status": "blocked", "reason": rb.reason, "id": signal.id},
        )

    # 5. Set leverage (always before placing order)
    leverage_ok = await bitget_client.set_leverage(signal.symbol, settings.DEFAULT_LEVERAGE)
    if not leverage_ok:
        msg = f"Failed to set leverage for {signal.symbol} — aborting order"
        logger.error(msg)
        await telegram_notifier.notify_error("set_leverage", msg)
        return JSONResponse(status_code=200, content={"status": "error", "reason": msg})

    # 6. Place order
    result = await bitget_client.place_order(signal)

    # 7. Record and notify
    if result.success:
        risk_manager.record_open(signal)

    record = ExecutionRecord(
        signal=signal,
        order_result=result,
        executed_at=datetime.now(timezone.utc).isoformat(),
        leverage_set=leverage_ok,
    )
    execution_log.append(record)

    await telegram_notifier.notify_execution(signal, result)

    response_status = "executed" if result.success else "failed"
    logger.info(f"Signal {signal.id}: {response_status}")

    return JSONResponse(
        status_code=200,
        content={
            "status": response_status,
            "id": signal.id,
            "order_id": result.order_id,
            "demo": result.demo_mode,
            "error": result.error,
        },
    )


# ── Manual close endpoint (for SL/TP management) ────────────────────────────

@app.post("/close/{symbol}")
async def manual_close(symbol: str, secret: str = Query(default="")):
    """
    Mark a symbol as closed in the bot's open position tracker.
    Call this after manually closing a trade on Bitget, or after TP3/SL hit.
    Does NOT place any order — just clears the bot's internal tracking.
    """
    if settings.WEBHOOK_SECRET and secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")

    risk_manager.record_closed(symbol.upper())
    return {"status": "cleared", "symbol": symbol.upper()}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
