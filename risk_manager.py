"""
SA-GAIP Bot — Risk Manager
Gates every signal before it reaches Bitget.
This is your last line of defense — it should be conservative.
"""
import logging
from datetime import datetime, timezone
from collections import deque

from models import SignalPayload
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory deduplication: store last N trade IDs seen this session
_recent_ids: deque = deque(maxlen=50)

# Track open signals per symbol to prevent double-entry
_open_symbols: dict[str, str] = {}  # symbol → trade_id


class RiskBlock(Exception):
    """Raised when a signal fails risk checks."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def validate(signal: SignalPayload) -> None:
    """
    Run all risk checks. Raises RiskBlock with a reason string if any check fails.
    Called before any order is placed.
    """
    # 1. Duplicate trade ID check
    if signal.id in _recent_ids:
        raise RiskBlock(f"Duplicate trade ID {signal.id} — already processed this signal")

    # 2. Score threshold
    abs_score = abs(signal.score)
    if abs_score < settings.MIN_SCORE_TO_EXECUTE:
        raise RiskBlock(
            f"Score {signal.score}/15 below minimum threshold ({settings.MIN_SCORE_TO_EXECUTE}). "
            f"Pine Script should already block these — this is a safety net."
        )

    # 3. Counter-trend block (optional, configurable)
    if settings.BLOCK_COUNTER_TREND and signal.is_counter_trend:
        raise RiskBlock(
            "Counter-trend signal blocked by BLOCK_COUNTER_TREND=true. "
            "If you want counter-trend trades, set BLOCK_COUNTER_TREND=false."
        )

    # 4. Already open on this symbol
    if signal.symbol in _open_symbols:
        existing_id = _open_symbols[signal.symbol]
        raise RiskBlock(
            f"Already have an open position on {signal.symbol} (trade {existing_id}). "
            f"Close existing position before opening a new one."
        )

    # 5. Validate SL is on the correct side of entry
    if signal.is_long and signal.sl >= signal.price:
        raise RiskBlock(
            f"Long signal SL ({signal.sl}) is above or at entry ({signal.price}). "
            f"Pine Script calculation error — rejecting."
        )
    if not signal.is_long and signal.sl <= signal.price:
        raise RiskBlock(
            f"Short signal SL ({signal.sl}) is below or at entry ({signal.price}). "
            f"Pine Script calculation error — rejecting."
        )

    # 6. Validate TP1 is on the correct side
    if signal.is_long and signal.tp1 <= signal.price:
        raise RiskBlock(f"Long TP1 ({signal.tp1}) is below entry ({signal.price}).")
    if not signal.is_long and signal.tp1 >= signal.price:
        raise RiskBlock(f"Short TP1 ({signal.tp1}) is above entry ({signal.price}).")

    # 7. Minimum position size
    if signal.size <= 0:
        raise RiskBlock(f"Position size {signal.size} is zero or negative.")

    # 8. Sanity check on risk distance (SL not absurdly far from entry)
    risk_pct = signal.risk_distance / signal.price * 100
    if risk_pct > 5.0:
        raise RiskBlock(
            f"Risk distance is {risk_pct:.1f}% of price — unusually wide SL. "
            f"Rejecting for safety. Verify Pine Script ATR buffer."
        )

    logger.info(
        f"Risk OK: {signal.id} | {signal.action.value.upper()} {signal.symbol} | "
        f"Score {signal.score} | {'COUNTER' if signal.is_counter_trend else 'ALIGNED'}"
    )


def record_open(signal: SignalPayload) -> None:
    """Call after a successful order placement to track open position."""
    _recent_ids.append(signal.id)
    _open_symbols[signal.symbol] = signal.id
    logger.info(f"Recorded open: {signal.symbol} → {signal.id}")


def record_closed(symbol: str) -> None:
    """Call when a position is closed (SL hit, TP3 hit, or manual close)."""
    if symbol in _open_symbols:
        trade_id = _open_symbols.pop(symbol)
        logger.info(f"Cleared open record: {symbol} ({trade_id})")


def get_open_symbols() -> dict:
    """Return current open symbol tracking dict."""
    return dict(_open_symbols)
