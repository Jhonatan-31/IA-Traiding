"""Realistic *virtual* execution helpers — no order book invention."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ExecutionAssumptions:
    fee_rate: float = 0.001
    base_slip_rate: float = 0.001
    spread_bps: float = 2.0  # estimated half-spread in bps each side if no book
    latency_bars: int = 1  # fill at open of t+latency
    # When True, we only claim book-backed fills if order_book snapshot provided
    require_book_for_claim: bool = True


def estimate_fill_price(
    *,
    side: str,
    mid_or_ref: float,
    assumptions: ExecutionAssumptions,
    bar_volume: float | None = None,
    order_qty: float | None = None,
    order_book: dict | None = None,
) -> dict[str, Any]:
    """
    Theoretical fill from mid/ref + spread + slip.
    If order_book is None, mark execution as 'theoretical_no_book'.
    Partial fills only when volume data supports a cap.
    """
    if mid_or_ref <= 0:
        return {
            "ok": False,
            "reason": "invalid_ref_price",
            "execution_class": "invalid",
        }

    half_spread = mid_or_ref * (assumptions.spread_bps / 10000.0)
    slip = mid_or_ref * assumptions.base_slip_rate

    # Variable slip: if order large vs bar volume, increase slip (still heuristic)
    vol_factor = 1.0
    partial = False
    fill_qty = order_qty
    if bar_volume is not None and order_qty is not None and bar_volume > 0:
        frac = order_qty / bar_volume
        if frac > 0.05:
            vol_factor += min(frac, 1.0)  # up to +100% slip
        if frac > 0.25:
            # Cap fill at 25% of bar volume — data-backed partial, not book depth
            fill_qty = bar_volume * 0.25
            partial = True

    if side.upper() == "BUY":
        raw = mid_or_ref + half_spread + slip * vol_factor
        fee = raw * assumptions.fee_rate
        px = raw * (1 + assumptions.fee_rate)
    else:
        raw = mid_or_ref - half_spread - slip * vol_factor
        fee = raw * assumptions.fee_rate
        px = raw * (1 - assumptions.fee_rate)

    execution_class = "theoretical_no_book"
    book_note = "No order-book depth available; fill is illustrative from mid/ref + spread/slip."
    if order_book is not None:
        # We do not invent levels — if caller passes a real snapshot, mark as book_backed
        # but still do not fabricate missing bids/asks.
        bids = order_book.get("bids") or []
        asks = order_book.get("asks") or []
        if side.upper() == "BUY" and asks:
            execution_class = "book_backed_top_of_book"
            book_note = "Used provided ask top-of-book; no deeper levels invented."
            top = float(asks[0][0])
            px = top * (1 + assumptions.fee_rate)
            fee = top * assumptions.fee_rate
        elif side.upper() == "SELL" and bids:
            execution_class = "book_backed_top_of_book"
            book_note = "Used provided bid top-of-book; no deeper levels invented."
            top = float(bids[0][0])
            px = top * (1 - assumptions.fee_rate)
            fee = top * assumptions.fee_rate
        else:
            execution_class = "theoretical_empty_book"
            book_note = "Order book provided but empty on needed side; fell back to theoretical."

    return {
        "ok": True,
        "price": float(px),
        "fee_component": float(fee),
        "slip_component": float(slip * vol_factor),
        "spread_component": float(half_spread),
        "fill_qty": float(fill_qty) if fill_qty is not None else None,
        "partial": partial,
        "execution_class": execution_class,
        "latency_bars": assumptions.latency_bars,
        "note": book_note,
    }


def decide_order_status(
    *,
    breaker_active: bool,
    breaker_reason: str | None,
    stale_data: bool,
    cash_ok: bool,
    fill: dict[str, Any],
) -> tuple[str, str]:
    if breaker_active:
        return "REJECTED", f"circuit_breaker:{breaker_reason}"
    if stale_data:
        return "REJECTED", "stale_market_data"
    if not cash_ok:
        return "REJECTED", "insufficient_cash"
    if not fill.get("ok"):
        return "REJECTED", str(fill.get("reason") or "fill_failed")
    if fill.get("partial"):
        return "PARTIAL", "volume_capped_partial"
    return "FILLED", "ok"
