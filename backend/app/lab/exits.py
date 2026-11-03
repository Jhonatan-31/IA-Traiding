"""Exit policy for lab positions — stop/tp/time/strategy; no stale marks."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(x) -> Decimal:
    return Decimal(str(x))


# Priority when multiple exit conditions could apply (first match wins):
# 1) missing/stale mark → no execution
# 2) stop_loss
# 3) take_profit
# 4) max_hold_bars (time stop)
# 5) strategy_exit (SMA SELL)
EXIT_PRIORITY = (
    "no_mark_price",
    "stale_mark_no_auto_exit",
    "stop_loss",
    "take_profit",
    "max_hold_bars",
    "strategy_exit",
)


def evaluate_exit(
    position: dict,
    *,
    mark_price: Decimal | None,
    mark_age_s: float | None,
    stale_s: float,
    strategy_side: str | None,
    bars_held: int | None,
) -> dict[str, Any]:
    """
    Returns action HOLD|SELL with reason.
    Distinguishes stop_trigger_price vs execution_price (caller applies slip on fill).
    Never assumes a fill at an unavailable mark.
    """
    if mark_price is None or mark_price <= 0:
        return {
            "action": "HOLD",
            "reason": "no_mark_price",
            "allow_execution": False,
            "priority": EXIT_PRIORITY.index("no_mark_price"),
        }
    if mark_age_s is not None and mark_age_s > stale_s:
        return {
            "action": "HOLD",
            "reason": "stale_mark_no_auto_exit",
            "allow_execution": False,
            "priority": EXIT_PRIORITY.index("stale_mark_no_auto_exit"),
        }

    entry = _d(position.get("entry_price") or 0)
    if entry <= 0:
        # cannot value SL/TP safely
        if strategy_side == "SELL":
            return {
                "action": "SELL",
                "reason": "strategy_exit",
                "allow_execution": True,
                "stop_triggered": False,
                "stop_trigger_price": None,
                "priority": EXIT_PRIORITY.index("strategy_exit"),
            }
        return {"action": "HOLD", "reason": "missing_entry_price", "allow_execution": False}

    sl_pct = _d(position.get("stop_loss_pct") or "0.02")
    tp_pct = _d(position.get("take_profit_pct") or "0.04")
    max_bars = int(position.get("max_hold_bars") or 48)
    sl_price = entry * (Decimal("1") - sl_pct)
    tp_price = entry * (Decimal("1") + tp_pct)

    if mark_price <= sl_price:
        return {
            "action": "SELL",
            "reason": "stop_loss",
            "allow_execution": True,
            "stop_triggered": True,
            "stop_trigger_price": float(sl_price),
            "priority": EXIT_PRIORITY.index("stop_loss"),
        }
    if mark_price >= tp_price:
        return {
            "action": "SELL",
            "reason": "take_profit",
            "allow_execution": True,
            "stop_triggered": True,
            "stop_trigger_price": float(tp_price),
            "priority": EXIT_PRIORITY.index("take_profit"),
        }
    if bars_held is not None and bars_held >= max_bars:
        return {
            "action": "SELL",
            "reason": "max_hold_bars",
            "allow_execution": True,
            "stop_triggered": False,
            "stop_trigger_price": None,
            "priority": EXIT_PRIORITY.index("max_hold_bars"),
        }
    if strategy_side == "SELL":
        return {
            "action": "SELL",
            "reason": "strategy_exit",
            "allow_execution": True,
            "stop_triggered": False,
            "stop_trigger_price": None,
            "priority": EXIT_PRIORITY.index("strategy_exit"),
        }
    return {"action": "HOLD", "reason": "no_exit", "allow_execution": False}
