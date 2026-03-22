"""
SA-GAIP Bot — Configuration
All secrets come from environment variables. Never hardcode credentials.
"""
import os
from functools import lru_cache


class Settings:
    # ── Bitget API ────────────────────────────────────────────────────────────
    BITGET_API_KEY: str = os.getenv("BITGET_API_KEY", "")
    BITGET_SECRET_KEY: str = os.getenv("BITGET_SECRET_KEY", "")
    BITGET_PASSPHRASE: str = os.getenv("BITGET_PASSPHRASE", "")
    BITGET_BASE_URL: str = os.getenv("BITGET_BASE_URL", "https://api.bitget.com")

    # Demo mode — set DEMO_MODE=false only when ready for live trading
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "true").lower() == "true"

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WAR_ROOM_CHAT_ID: str = os.getenv("TELEGRAM_WAR_ROOM_CHAT_ID", "")

    # ── Webhook security ──────────────────────────────────────────────────────
    # Set a random secret string and add it as ?secret=XXX in TradingView webhook URL
    WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")

    # ── Risk rules ────────────────────────────────────────────────────────────
    # Minimum score required to execute a trade (Pine Script scores -15 to +15)
    MIN_SCORE_TO_EXECUTE: float = float(os.getenv("MIN_SCORE_TO_EXECUTE", "4.0"))

    # Skip counter-trend signals (set to "false" to allow them)
    BLOCK_COUNTER_TREND: bool = os.getenv("BLOCK_COUNTER_TREND", "false").lower() == "true"

    # Default leverage for all trades
    DEFAULT_LEVERAGE: int = int(os.getenv("DEFAULT_LEVERAGE", "10"))

    # Maximum position size cap (in units/coins) — safety ceiling
    MAX_POSITION_SIZE: float = float(os.getenv("MAX_POSITION_SIZE", "1.0"))

    # ── App ───────────────────────────────────────────────────────────────────
    PORT: int = int(os.getenv("PORT", "8000"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self) -> list[str]:
        """Return list of missing required config keys."""
        missing = []
        if not self.BITGET_API_KEY:
            missing.append("BITGET_API_KEY")
        if not self.BITGET_SECRET_KEY:
            missing.append("BITGET_SECRET_KEY")
        if not self.BITGET_PASSPHRASE:
            missing.append("BITGET_PASSPHRASE")
        if not self.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.TELEGRAM_WAR_ROOM_CHAT_ID:
            missing.append("TELEGRAM_WAR_ROOM_CHAT_ID")
        return missing


@lru_cache()
def get_settings() -> Settings:
    return Settings()
