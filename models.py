"""
SA-GAIP Bot — Data Models
These match the JSON payload fired by Section 27 of the Pine Script exactly.
"""
from pydantic import BaseModel, field_validator
from typing import Optional
from enum import Enum


class SignalAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class SignalPayload(BaseModel):
    """
    Matches the Bitget JSON from Pine Script Section 27:
    {"action","size","symbol","price","sl","tp1","id","score","sync"}
    """
    action: SignalAction
    size: float          # position size calculated by Pine risk model
    symbol: str          # e.g. "XAUUSDT", "ETHUSDT", "BTCUSDT"
    price: float         # entry price (close at signal bar)
    sl: float            # stop loss price
    tp1: float           # take profit 1 (1:1 R:R)
    id: str              # trade ID e.g. ATM-20260322-0815-BUY-01
    score: float         # composite score -15 to +15
    sync: str            # 4-layer sync description

    @field_validator("size", "price", "sl", "tp1", mode="before")
    @classmethod
    def parse_numeric(cls, v):
        return float(str(v).replace(",", ""))

    @property
    def risk_distance(self) -> float:
        """Price distance from entry to SL."""
        return abs(self.price - self.sl)

    @property
    def tp2(self) -> float:
        """TP2 at 1.5:1 R:R — Pine Script doesn't send this, we compute it."""
        if self.action == SignalAction.BUY:
            return self.price + self.risk_distance * 1.5
        return self.price - self.risk_distance * 1.5

    @property
    def tp3(self) -> float:
        """TP3 at 2:1 R:R — Pine Script doesn't send this, we compute it."""
        if self.action == SignalAction.BUY:
            return self.price + self.risk_distance * 2.0
        return self.price - self.risk_distance * 2.0

    @property
    def is_long(self) -> bool:
        return self.action == SignalAction.BUY

    @property
    def is_counter_trend(self) -> bool:
        return "COUNTER" in self.sync.upper()

    @property
    def is_sync4(self) -> bool:
        return "4-LAYER" in self.sync.upper() or "SYNC4" in self.sync.upper()


class OrderResult(BaseModel):
    """Result from Bitget after placing an order."""
    success: bool
    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    error: Optional[str] = None
    demo_mode: bool = False


class ExecutionRecord(BaseModel):
    """Full record of a signal execution, stored in memory for the session."""
    signal: SignalPayload
    order_result: OrderResult
    executed_at: str
    leverage_set: bool = False
