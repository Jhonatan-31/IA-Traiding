"""Experimento controlado V1 vs V2 — mismas decisiones hipotéticas.

No muta ledgers. Casos sin BBO fresco → NO_COMPARABLE (nunca sustituye V1 en silencio).
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Any

from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from .bbo_store import BboQuote
from .engine_v2 import ExecutionV2Assumptions, simulate_fill_v2


@dataclass
class HypotheticalDecision:
    decision_ts_ms: int
    symbol: str
    side: str
    qty: float
    ref_mid: float
    order_type: str = "MARKET_TAKER"
    capital: float = 1000.0
    assumed_send_latency_ms: int = 0  # hypothetical — labeled analysis only


def evaluate_pair(
    decision: HypotheticalDecision,
    bbo: BboQuote | None,
    *,
    v1: ExecutionAssumptions | None = None,
    v2: ExecutionV2Assumptions | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    now = int(now_ms if now_ms is not None else time.time() * 1000)
    v1_a = v1 or ExecutionAssumptions()
    v2_a = v2 or ExecutionV2Assumptions()
    v1_fill = estimate_fill_price(
        side=decision.side,
        mid_or_ref=decision.ref_mid,
        assumptions=v1_a,
        order_qty=decision.qty,
    )
    base = {
        "decision_ts_ms": decision.decision_ts_ms,
        "symbol": decision.symbol,
        "side": decision.side.upper(),
        "qty_requested": decision.qty,
        "ref_mid": decision.ref_mid,
        "order_type": decision.order_type,
        "assumed_send_latency_ms": decision.assumed_send_latency_ms,
        "latency_note": "assumed_send_latency_ms is hypothetical analysis, not measured Binance RTT",
        "v1": v1_fill,
    }
    if bbo is None:
        return {
            **base,
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": "missing_bbo",
            "v2": None,
        }
    # Quote age at decision time (if decision in past relative to quote receive)
    age_at_decision = max(0, decision.decision_ts_ms - bbo.received_at_ms)
    # Prefer age from now if decision is "now"
    age_now = bbo.age_ms(now)
    if bbo.is_stale(v2_a.max_quote_age_ms, now_ms=now):
        return {
            **base,
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": "stale_bbo",
            "bbo_age_ms": age_now,
            "v2": {"ok": False, "reason": "stale_bbo", "age_ms": age_now},
        }
    v2_fill = simulate_fill_v2(
        side=decision.side,
        qty=decision.qty,
        ref_mid=decision.ref_mid,
        bbo=bbo,
        assumptions=v2_a,
        now_ms=now,
    )
    if not v2_fill.get("ok"):
        return {
            **base,
            "comparable": False,
            "status": "NO_COMPARABLE",
            "reason": v2_fill.get("reason"),
            "v2": v2_fill,
            "bbo_age_ms": age_now,
            "quote_age_at_decision_ms": age_at_decision,
        }

    px1 = float(v1_fill["price"])
    px2 = float(v2_fill["price_all_in"])
    fq = float(v2_fill["fill_qty"])
    if decision.side.upper() == "BUY":
        price_diff = px2 - px1  # positive ⇒ V2 more expensive to buy
        cost_diff = price_diff * fq
    else:
        price_diff = px1 - px2  # positive ⇒ V1 credited more than V2
        cost_diff = price_diff * fq

    # Avoid double-counting narrative: V2 executable already is ask/bid (spread vs mid).
    spread_already_in_executable = True
    return {
        **base,
        "comparable": True,
        "status": "OK",
        "v2": v2_fill,
        "bbo": bbo.to_public_dict(now_ms=now, max_age_ms=v2_a.max_quote_age_ms),
        "bbo_age_ms": age_now,
        "price_v1": px1,
        "price_v2": px2,
        "price_diff_v2_minus_v1_signed": float(px2 - px1),
        "cost_gap_adverse_to_trader": float(cost_diff),
        "spread_abs": v2_fill.get("spread_abs"),
        "fee_v2": v2_fill.get("fee_total"),
        "slip_v2": v2_fill.get("slip_total"),
        "qty_executable_est": fq,
        "partial": v2_fill.get("partial"),
        "top_qty_cover_pct": (
            None
            if decision.qty <= 0
            else min(1.0, fq / decision.qty)
        ),
        "accounting_note": (
            "Spread vs mid is embodied in ask/bid executable; fee is separate. "
            f"spread_already_in_executable={spread_already_in_executable}"
        ),
    }


def summarize_pairs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    comp = [r for r in rows if r.get("comparable")]
    ncomp = [r for r in rows if not r.get("comparable")]
    price_diffs = [float(r["price_diff_v2_minus_v1_signed"]) for r in comp]
    cost_gaps = [float(r["cost_gap_adverse_to_trader"]) for r in comp]
    rejects = [r for r in rows if (r.get("v2") or {}).get("ok") is False]

    def _med(xs: list[float]) -> float | None:
        return float(statistics.median(xs)) if xs else None

    return {
        "n_total": len(rows),
        "n_comparable": len(comp),
        "n_not_comparable": len(ncomp),
        "pct_not_comparable": (len(ncomp) / len(rows)) if rows else None,
        "n_v2_reject_or_fail": len(rejects),
        "median_price_diff_v2_minus_v1": _med(price_diffs),
        "median_cost_gap_adverse": _med(cost_gaps),
        "not_comparable_reasons": {
            k: sum(1 for r in ncomp if r.get("reason") == k)
            for k in sorted({str(r.get("reason")) for r in ncomp})
        },
        "interpretation": (
            "Positive median price_diff on BUY means V2 (ask) costs more than V1 mid+proxy. "
            "That is a precision signal, not proof of economic superiority by itself."
        ),
        "fabricated_observations": False,
    }
