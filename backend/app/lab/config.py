"""Lab paper trading risk/config — documented thresholds."""
from __future__ import annotations

from decimal import Decimal

from . import AUTHORIZED_STRATEGY, LAB_ACCOUNT_ID

ACCOUNT_ID = LAB_ACCOUNT_ID
STRATEGY = AUTHORIZED_STRATEGY
BUDGET = Decimal("25")
MIN_BUDGET = Decimal("10")
MAX_POSITIONS = 10
FEE_RATE = Decimal("0.001")
SLIP_RATE = Decimal("0.001")
MAX_DAILY_LOSS_PCT = Decimal("0.02")
MAX_DRAWDOWN_PCT = Decimal("0.10")
STOP_LOSS_PCT = Decimal("0.02")
TAKE_PROFIT_PCT = Decimal("0.04")
MAX_HOLD_BARS = 48
PRICE_STALE_S = 7200
MIN_QUOTE_VOLUME = Decimal("1000000")
INTERVAL_MS = 3_600_000
