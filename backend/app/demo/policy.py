"""Frozen DEMO policy v1 — do not retune from live outcomes."""
from __future__ import annotations

from . import POLICY_VERSION as POLICY_VERSION  # noqa: F401 — re-export
from . import SYMBOLS

SYMBOLS_TUPLE = SYMBOLS

MAX_POS_USDT = 25.0
MAX_POSITIONS = 3
MAX_EXPOSURE_USDT = 75.0
STOP_LOSS_PCT = 0.01
TAKE_PROFIT_PCT = 0.02
PEAK_DD_PAUSE_PCT = 0.03

FEE_RATE = 0.001
SLIP_RATE = 0.0005

RSI_BUY_LO = 40.0
RSI_BUY_HI = 70.0
ATR_PCT_MAX = 0.02
BUY_MIN_FLAGS = 4  # of 5
BUY_SCORE_MIN = 0.80
RSI_EXIT = 42.0

POLICY_DOC = "docs/DEMO_POLICY_v1.md"
