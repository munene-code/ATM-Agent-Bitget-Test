"""
SA-GAIP Bot — Telegram Notifier
Sends execution confirmations and error alerts to the War Room channel.
This is OUTBOUND only — the bot posts confirmations, it does not read signals from Telegram.
"""
import httpx
import logging
from datetime import datetime, timezone

from models import SignalPayload, OrderResult
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TELEGRAM_API = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"

SEP  = "━━━━━━━━━━━━━━━━━━━━━"
SEP2 = "─────────────────────"


def _fmt(v: float, decimals: int = 2) -> str:
    return f"{v:.{decimals}f}"


async def send_message(text: str, chat_id: str = None) -> bool:
    """Send a plain text message to the War Room channel."""
    target = chat_id or settings.TELEGRAM_WAR_ROOM_CHAT_ID
    if not target or not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram not configured — skipping notification")
        return False

    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "HTML",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(TELEGRAM_API, json=payload)
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"Telegram send failed: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Telegram send exception: {e}")
        return False


async def notify_execution(signal: SignalPayload, result: OrderResult) -> None:
    """Send a full execution confirmation card to the War Room."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    demo_tag = " [DEMO]" if result.demo_mode else ""
    direction = "🟢 LONG" if signal.is_long else "🔴 SHORT"
    sync_tag = "🔥 SYNC4" if signal.is_sync4 else ("⚠️ COUNTER" if signal.is_counter_trend else "LOCAL")

    if result.success:
        header = f"✅ ORDER PLACED{demo_tag}"
        order_line = f"Order ID   : <code>{result.order_id or result.client_order_id}</code>"
    else:
        header = f"❌ ORDER FAILED{demo_tag}"
        order_line = f"Error      : {result.error}"

    msg = (
        f"{SEP}\n"
        f"🤖 SA-GAIP PYTHON EXECUTOR\n"
        f"{SEP}\n"
        f"🔔 EVENT: {header}\n"
        f"{SEP2}\n"
        f"Asset      : {signal.symbol}\n"
        f"Direction  : {direction}\n"
        f"Signal     : {sync_tag}\n"
        f"Score      : {signal.score}/15\n"
        f"{SEP2}\n"
        f"Entry      : {_fmt(signal.price)}\n"
        f"Stop Loss  : {_fmt(signal.sl)}\n"
        f"TP1 (1:1)  : {_fmt(signal.tp1)}\n"
        f"TP2 (1.5:1): {_fmt(signal.tp2)}\n"
        f"TP3 (2:1)  : {_fmt(signal.tp3)}\n"
        f"Size       : {signal.size}\n"
        f"{SEP2}\n"
        f"{order_line}\n"
        f"Trade ID   : <code>{signal.id}</code>\n"
        f"Sync       : {signal.sync}\n"
        f"Time       : {ts}\n"
        f"{SEP}\n"
        f"⚠️ Not financial advice. © 2026 Absolute Dollar"
    )
    await send_message(msg)


async def notify_risk_block(signal: SignalPayload, reason: str) -> None:
    """Notify War Room when a signal is blocked by the risk manager."""
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    direction = "🟢 LONG" if signal.is_long else "🔴 SHORT"
    msg = (
        f"{SEP2}\n"
        f"🛑 SIGNAL BLOCKED BY PYTHON RISK MANAGER\n"
        f"{SEP2}\n"
        f"Asset    : {signal.symbol}\n"
        f"Dir      : {direction}\n"
        f"Score    : {signal.score}/15\n"
        f"Reason   : {reason}\n"
        f"ID       : <code>{signal.id}</code>\n"
        f"Time     : {ts}\n"
        f"{SEP2}"
    )
    await send_message(msg)


async def notify_startup(demo_mode: bool, missing_keys: list) -> None:
    """Send startup status to War Room."""
    status = "🟡 DEMO MODE — no real funds" if demo_mode else "🔴 LIVE MODE — real funds at risk"
    if missing_keys:
        body = f"⚠️ Missing config keys: {', '.join(missing_keys)}\nBot is NOT operational."
    else:
        body = "✅ All credentials loaded. Webhook is live and listening."

    msg = (
        f"{SEP}\n"
        f"🚀 SA-GAIP PYTHON BOT — STARTED\n"
        f"{SEP}\n"
        f"Mode   : {status}\n"
        f"{body}\n"
        f"{SEP}"
    )
    await send_message(msg)


async def notify_error(context: str, error: str) -> None:
    """Send unexpected error alert to War Room."""
    ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
    msg = (
        f"⚠️ SA-GAIP BOT ERROR\n"
        f"Context : {context}\n"
        f"Error   : {error}\n"
        f"Time    : {ts}"
    )
    await send_message(msg)
