"""Motor de ejecución virtual V2 — precios ejecutables conservadores.

No muta ledgers. No reemplaza estimate_fill_price (V1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from .bbo_store import BboQuote


@dataclass
class ExecutionV2Assumptions:
    fee_rate: float = 0.001  # taker spot retail típico
    extra_slip_rate: float = 0.0002  # slip adicional más allá del BBO (impacto/latencia)
    max_quote_age_ms: int = 5000
    # Sin profundidad: no asumir que top-of-book absorbe más que top qty
    respect_top_qty: bool = True
    reject_crossed_or_invalid: bool = True
    # Si no hay BBO: NO inventar bid/ask; marcar incertidumbre
    allow_mid_fallback: bool = False


def simulate_fill_v2(
    *,
    side: str,
    qty: float,
    ref_mid: float | None = None,
    bbo: BboQuote | None = None,
    assumptions: ExecutionV2Assumptions | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """
    BUY → ask (+ fee + optional slip). SELL → bid (− fee − optional slip).
    Stale/missing BBO → reject or explicit uncertainty (never silently treat as fresh).
    """
    a = assumptions or ExecutionV2Assumptions()
    side_u = side.upper()
    if qty is None or float(qty) <= 0:
        return {"ok": False, "reason": "invalid_qty", "engine": "v2"}
    qty = float(qty)

    if bbo is not None and bbo.is_stale(a.max_quote_age_ms, now_ms=now_ms):
        return {
            "ok": False,
            "reason": "stale_bbo",
            "engine": "v2",
            "age_ms": bbo.age_ms(now_ms),
            "max_quote_age_ms": a.max_quote_age_ms,
            "data_quality": "STALE",
        }

    fill_qty = qty
    partial = False
    uncertainty = []
    execution_class = "unknown"

    if bbo is not None:
        if a.reject_crossed_or_invalid and (bbo.ask_price < bbo.bid_price or bbo.bid_price <= 0):
            return {"ok": False, "reason": "invalid_bbo", "engine": "v2", "data_quality": "INVALID"}
        top_qty = bbo.ask_qty if side_u == "BUY" else bbo.bid_qty
        if a.respect_top_qty and top_qty > 0 and qty > top_qty:
            fill_qty = float(top_qty)
            partial = True
            uncertainty.append("size_exceeds_top_of_book_qty")
        if side_u == "BUY":
            raw = float(bbo.ask_price) * (1.0 + a.extra_slip_rate)
            fee_per_unit = raw * a.fee_rate
            px_all_in = raw * (1.0 + a.fee_rate)
            ref = bbo.mid
            executable = float(bbo.ask_price)
        else:
            raw = float(bbo.bid_price) * (1.0 - a.extra_slip_rate)
            fee_per_unit = raw * a.fee_rate
            px_all_in = raw * (1.0 - a.fee_rate)
            ref = bbo.mid
            executable = float(bbo.bid_price)
        execution_class = "bbo_top_of_book"
        data_quality = "LIVE_BBO"
        spread_abs = bbo.spread_abs
        spread_rel = bbo.spread_rel
    else:
        if not a.allow_mid_fallback or ref_mid is None or ref_mid <= 0:
            return {
                "ok": False,
                "reason": "missing_bbo",
                "engine": "v2",
                "data_quality": "MISSING_BBO",
                "note": "V2 no inventa bid/ask históricos. Use V1 teórico solo con etiqueta explícita.",
            }
        # Fallback explícito (opt-in): mid + incertidumbre alta — no se presenta como BBO
        uncertainty.append("mid_fallback_no_book")
        half = float(ref_mid) * 0.0001  # 1 bp proxy marcado como incierto
        if side_u == "BUY":
            executable = float(ref_mid) + half
            raw = executable * (1.0 + a.extra_slip_rate)
            fee_per_unit = raw * a.fee_rate
            px_all_in = raw * (1.0 + a.fee_rate)
        else:
            executable = float(ref_mid) - half
            raw = executable * (1.0 - a.extra_slip_rate)
            fee_per_unit = raw * a.fee_rate
            px_all_in = raw * (1.0 - a.fee_rate)
        ref = float(ref_mid)
        spread_abs = 2 * half
        spread_rel = spread_abs / ref if ref else float("nan")
        execution_class = "mid_fallback_uncertain"
        data_quality = "UNCERTAIN_NO_BBO"

    notional = fill_qty * raw
    fee_total = fill_qty * fee_per_unit
    slip_total = fill_qty * abs(raw - executable)
    spread_cost = fill_qty * (spread_abs / 2.0)

    return {
        "ok": True,
        "engine": "v2",
        "side": side_u,
        "ref_price": float(ref),
        "executable_price": float(executable),
        "raw_price": float(raw),
        "price_all_in": float(px_all_in),
        "qty_requested": qty,
        "fill_qty": float(fill_qty),
        "partial": partial,
        "fee_total": float(fee_total),
        "slip_total": float(slip_total),
        "spread_abs": float(spread_abs),
        "spread_rel": float(spread_rel),
        "spread_cost_est": float(spread_cost),
        "notional_raw": float(notional),
        "total_cost_est": float(fee_total + slip_total + spread_cost),
        "cash_delta": float(-(fill_qty * px_all_in) if side_u == "BUY" else (fill_qty * px_all_in)),
        "execution_class": execution_class,
        "data_quality": data_quality,
        "uncertainty": uncertainty,
        "note": (
            "Top-of-book no garantiza profundidad completa; "
            "partial=true si qty > top qty conocida."
        ),
    }


def compare_v1_v2(
    *,
    side: str,
    qty: float,
    ref_mid: float,
    bbo: BboQuote | None = None,
    v1: ExecutionAssumptions | None = None,
    v2: ExecutionV2Assumptions | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Side-by-side V1 (mid+proxy) vs V2 (BBO). Does not write ledgers."""
    v1_a = v1 or ExecutionAssumptions()
    v1_fill = estimate_fill_price(
        side=side,
        mid_or_ref=ref_mid,
        assumptions=v1_a,
        order_qty=qty,
    )
    v2_fill = simulate_fill_v2(
        side=side,
        qty=qty,
        ref_mid=ref_mid,
        bbo=bbo,
        assumptions=v2 or ExecutionV2Assumptions(),
        now_ms=now_ms,
    )
    pl_delta = None
    if v1_fill.get("ok") and v2_fill.get("ok"):
        # Diferencia de precio all-in * qty (BUY: V2 más caro ⇒ P/L peor)
        px1 = float(v1_fill["price"])
        px2 = float(v2_fill["price_all_in"])
        fq = float(v2_fill["fill_qty"])
        if side.upper() == "BUY":
            pl_delta = (px1 - px2) * fq  # negativo si V2 peor para comprador
        else:
            pl_delta = (px2 - px1) * fq
    return {
        "v1": v1_fill,
        "v2": v2_fill,
        "pl_delta_v2_minus_model_gap": pl_delta,
        "interpretation": (
            "pl_delta_v2_minus_model_gap < 0 en BUY suele indicar que el mid+proxy V1 "
            "era optimista frente a ask real."
        ),
        "engines_preserved": {"v1": "prospect.execution", "v2": "execution_v2"},
    }
