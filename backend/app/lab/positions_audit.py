"""Open-position audit for lab exits — mark vs simulated execution, exit limits."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .config import FEE_RATE, INTERVAL_MS, SLIP_RATE


def _d(x) -> Decimal:
    return Decimal(str(x))


def enrich_position(
    pos: dict[str, Any],
    mark: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    fee_rate: Decimal = FEE_RATE,
    slip_rate: Decimal = SLIP_RATE,
    interval_ms: int = INTERVAL_MS,
) -> dict[str, Any]:
    """
    Enrich a lab_positions row (optionally already MTM'd) with exit levels.
    Distinguishes observed mark from estimated sell execution (mark − slip).
    """
    now = now or datetime.now(timezone.utc)
    entry = _d(pos.get("entry_price") or 0)
    sl_pct = _d(pos.get("stop_loss_pct") or "0.02")
    tp_pct = _d(pos.get("take_profit_pct") or "0.04")
    max_bars = int(pos.get("max_hold_bars") or 48)
    opened_ms = pos.get("opened_candle_ms")
    bars_held = None
    bars_remaining = None
    if opened_ms is not None:
        now_ms = int(now.timestamp() * 1000)
        bars_held = max(0, int((now_ms - int(opened_ms)) // interval_ms))
        bars_remaining = max(0, max_bars - bars_held)

    sl_price = float(entry * (Decimal("1") - sl_pct)) if entry > 0 else None
    tp_price = float(entry * (Decimal("1") + tp_pct)) if entry > 0 else None

    mark = mark or {}
    mark_ok = bool(mark.get("ok") and mark.get("price") is not None)
    mark_px = float(mark["price"]) if mark_ok else None
    # Simulated sell execution estimate (not a fill): adverse slip on sell
    est_exec = None
    est_fee = None
    if mark_ok and mark_px and mark_px > 0:
        est_exec = float(_d(mark_px) * (Decimal("1") - slip_rate))
        qty = _d(pos.get("qty") or 0)
        est_fee = float(qty * _d(est_exec) * fee_rate)

    out = dict(pos)
    out.update(
        {
            "stop_loss_price": sl_price,
            "take_profit_price": tp_price,
            "stop_loss_pct": float(sl_pct),
            "take_profit_pct": float(tp_pct),
            "max_hold_bars": max_bars,
            "bars_held": bars_held,
            "bars_remaining": bars_remaining,
            "opened_at": pos.get("opened_at"),
            "opened_candle_ms": opened_ms,
            "mark_price_observed": mark_px if mark_ok else pos.get("mark_price"),
            "mark_source": mark.get("source") or pos.get("mark_source"),
            "mark_at": mark.get("at") or pos.get("mark_at"),
            "data_status": "ok" if mark_ok or pos.get("complete") else (
                mark.get("reason") or pos.get("reason") or "mark_unavailable"
            ),
            "estimated_sell_execution_price": est_exec,
            "estimated_sell_fee": est_fee,
            "price_note": (
                "mark_price_observed = ticker público; "
                "estimated_sell_execution_price = mark − slip teórico (no es fill)."
            ),
        }
    )
    return out


def enrich_positions(
    positions: list[dict[str, Any]],
    marks: dict[str, dict[str, Any]] | None = None,
    **kwargs,
) -> list[dict[str, Any]]:
    marks = marks or {}
    return [enrich_position(p, marks.get(p.get("symbol") or ""), **kwargs) for p in positions]
