"""Frozen express policy — do not tune from this test's outcomes."""
from __future__ import annotations

from datetime import datetime, timezone

from . import END_UTC_ISO, SYMBOLS

END_UTC = datetime.fromisoformat(END_UTC_ISO)
SYMBOLS_TUPLE = SYMBOLS

# Risk
MAX_POS_USDT = 10.0
MAX_POSITIONS = 2
MAX_EXPOSURE_USDT = 20.0
STOP_LOSS_PCT = 0.01
TAKE_PROFIT_PCT = 0.02
PEAK_DD_PAUSE_PCT = 0.02  # pause buys if equity <= peak * (1 - this)

# Costs
FEE_RATE = 0.001
SLIP_RATE = 0.0005

# Signal
RSI_BUY_LO = 45.0
RSI_BUY_HI = 68.0
ATR_PCT_MAX = 0.015
BUY_SCORE_MIN = 0.80  # requires all 5 conditions → score 1.0; kept for clarity
STALE_PRICE_MS = 90_000

POLICY_VERSION = "express_v1_20261103_frozen"
POLICY_DOC = "docs/EXPRESS_POLICY_20261103.md"


def is_ended(now: datetime | None = None) -> bool:
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return n >= END_UTC


def seconds_remaining(now: datetime | None = None) -> float:
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return max(0.0, (END_UTC - n).total_seconds())
