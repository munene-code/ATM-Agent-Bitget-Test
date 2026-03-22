"""
SA-GAIP Bot — Bitget API Client (v2)
Handles authentication, leverage setting, and order placement.
Demo mode is controlled by DEMO_MODE env var — adds paptrading:1 header.
"""
import hmac
import hashlib
import base64
import time
import json
import logging
import httpx
from typing import Optional

from config import get_settings
from models import SignalPayload, OrderResult, SignalAction

logger = logging.getLogger(__name__)
settings = get_settings()

PRODUCT_TYPE = "USDT-FUTURES"


def _sign(timestamp: str, method: str, request_path: str, body: str = "") -> str:
    """
    Bitget HMAC-SHA256 signature.
    Message = timestamp + METHOD + requestPath + body
    """
    message = timestamp + method.upper() + request_path + body
    mac = hmac.new(
        settings.BITGET_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


def _headers(method: str, path: str, body: str = "") -> dict:
    """Build authenticated headers for every request."""
    ts = str(int(time.time() * 1000))
    headers = {
        "ACCESS-KEY": settings.BITGET_API_KEY,
        "ACCESS-SIGN": _sign(ts, method, path, body),
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-PASSPHRASE": settings.BITGET_PASSPHRASE,
        "Content-Type": "application/json",
        "locale": "en-US",
    }
    # Demo / paper trading mode — Bitget simulates execution, no real funds moved
    if settings.DEMO_MODE:
        headers["paptrading"] = "1"
    return headers


async def set_leverage(symbol: str, leverage: int) -> bool:
    """
    Set leverage for a symbol before placing any order.
    Must be called before every new position, not after.
    """
    path = "/api/v2/mix/account/set-leverage"
    body = json.dumps({
        "symbol": symbol,
        "productType": PRODUCT_TYPE,
        "marginCoin": "USDT",
        "leverage": str(leverage),
    })
    url = settings.BITGET_BASE_URL + path
    headers = _headers("POST", path, body)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            data = resp.json()
            if data.get("code") == "00000":
                logger.info(f"Leverage set: {symbol} → {leverage}x [demo={settings.DEMO_MODE}]")
                return True
            else:
                logger.warning(f"Leverage set failed: {data}")
                return False
    except Exception as e:
        logger.error(f"set_leverage error: {e}")
        return False


async def place_order(signal: SignalPayload) -> OrderResult:
    """
    Place a perpetual futures limit order with preset SL and TP1.
    TP2 and TP3 are managed manually per the semi-auto protocol.

    Side mapping:
      BUY  (long)  → side="buy",  tradeSide="open"
      SELL (short) → side="sell", tradeSide="open"
    """
    path = "/api/v2/mix/order/place-order"

    # Cap size at safety ceiling
    safe_size = min(signal.size, settings.MAX_POSITION_SIZE)

    order_body = {
        "symbol": signal.symbol,
        "productType": PRODUCT_TYPE,
        "marginMode": "isolated",
        "marginCoin": "USDT",
        "size": str(round(safe_size, 4)),
        "price": str(signal.price),
        "side": "buy" if signal.is_long else "sell",
        "tradeSide": "open",
        "orderType": "limit",
        "timeInForceValue": "gtc",
        "clientOid": signal.id,
        "presetStopLossPrice": str(signal.sl),
        "presetStopSurplusPrice": str(signal.tp1),
    }

    body = json.dumps(order_body)
    url = settings.BITGET_BASE_URL + path
    headers = _headers("POST", path, body)

    logger.info(
        f"Placing {'DEMO ' if settings.DEMO_MODE else ''}order: "
        f"{signal.action.value.upper()} {safe_size} {signal.symbol} "
        f"@ {signal.price} | SL {signal.sl} | TP1 {signal.tp1}"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            data = resp.json()

        if data.get("code") == "00000":
            order_data = data.get("data", {})
            return OrderResult(
                success=True,
                order_id=order_data.get("orderId"),
                client_order_id=order_data.get("clientOid", signal.id),
                demo_mode=settings.DEMO_MODE,
            )
        else:
            error_msg = data.get("msg", "Unknown Bitget error")
            logger.error(f"Order failed: {error_msg} | body: {data}")
            return OrderResult(success=False, error=error_msg, demo_mode=settings.DEMO_MODE)

    except httpx.TimeoutException:
        msg = "Bitget API timeout — order may or may not have been placed"
        logger.error(msg)
        return OrderResult(success=False, error=msg, demo_mode=settings.DEMO_MODE)
    except Exception as e:
        logger.error(f"place_order exception: {e}")
        return OrderResult(success=False, error=str(e), demo_mode=settings.DEMO_MODE)


async def get_account_balance() -> Optional[dict]:
    """Fetch USDT futures account equity — used for health checks."""
    path = "/api/v2/mix/account/accounts"
    params = f"?productType={PRODUCT_TYPE}"
    full_path = path + params
    url = settings.BITGET_BASE_URL + full_path
    headers = _headers("GET", full_path)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()
        if data.get("code") == "00000":
            accounts = data.get("data", [])
            for acc in accounts:
                if acc.get("marginCoin") == "USDT":
                    return {
                        "equity": acc.get("usdtEquity"),
                        "available": acc.get("available"),
                        "demo": settings.DEMO_MODE,
                    }
    except Exception as e:
        logger.error(f"get_account_balance error: {e}")
    return None


async def get_open_positions(symbol: Optional[str] = None) -> list:
    """Return list of open positions, optionally filtered by symbol."""
    path = "/api/v2/mix/position/all-position"
    params = f"?productType={PRODUCT_TYPE}"
    if symbol:
        params += f"&symbol={symbol}"
    full_path = path + params
    url = settings.BITGET_BASE_URL + full_path
    headers = _headers("GET", full_path)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()
        if data.get("code") == "00000":
            return data.get("data", [])
    except Exception as e:
        logger.error(f"get_open_positions error: {e}")
    return []
