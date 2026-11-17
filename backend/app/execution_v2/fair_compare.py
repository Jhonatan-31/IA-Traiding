"""AN2–AN3 — LEGACY vs MATCHED comparisons; desglose por símbolo/dirección/tamaño."""
from __future__ import annotations

import statistics
from collections import defaultdict
from decimal import Decimal
from typing import Any

from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from .am_experiment import (
    DEFAULT_SIZES,
    SizeScenario,
    _quote_from_event,
    qty_from_notional,
    subsample_by_bucket,
)
from .bbo_store import BboQuote
from .cost_contract import (
    CONTRACT_ID,
    CONTRACT_SPEC,
    D,
    bps,
    buy_all_in,
    components_to_dict,
    sell_all_in,
)
from .engine_v2 import ExecutionV2Assumptions, simulate_fill_v2

Mode = str  # LEGACY | MATCHED


def _pctiles(xs: list[float]) -> dict[str, float | None]:
    if not xs:
        return {"p5": None, "p25": None, "p50": None, "p75": None, "p95": None, "max": None, "n": 0}

    def q(p: int) -> float:
        if len(xs) >= 20:
            return float(statistics.quantiles(xs, n=100)[p - 1])
        s = sorted(xs)
        return float(s[0] if p <= 50 else s[-1])

    return {
        "n": len(xs),
        "p5": q(5),
        "p25": q(25) if len(xs) >= 4 else float(sorted(xs)[0]),
        "p50": float(statistics.median(xs)),
        "p75": q(75) if len(xs) >= 4 else float(sorted(xs)[-1]),
        "p95": q(95),
        "max": float(max(xs)),
    }


def evaluate_legacy(
    *,
    side: str,
    qty: float,
    mid: float,
    bbo: BboQuote,
    now_ms: int,
) -> dict[str, Any]:
    """V1/V2 con defaults de producción actuales (sin modificar legacy)."""
    v1_a = ExecutionAssumptions()  # slip 10bps, spread 2bps, fee 10bps
    v2_a = ExecutionV2Assumptions()  # extra_slip 2bps, fee 10bps
    v1 = estimate_fill_price(side=side, mid_or_ref=mid, assumptions=v1_a, order_qty=qty)
    v2 = simulate_fill_v2(
        side=side, qty=qty, ref_mid=mid, bbo=bbo, assumptions=v2_a, now_ms=now_ms
    )
    return _pack_row(
        mode="LEGACY",
        side=side,
        qty=qty,
        mid=mid,
        bbo=bbo,
        v1_fill=v1,
        v2_fill=v2,
        param_note={
            "v1": {"fee": 0.001, "base_slip": 0.001, "spread_bps": 2.0},
            "v2": {"fee": 0.001, "extra_slip": 0.0002},
            "not_bbo_value_isolation": True,
        },
    )


def evaluate_matched(
    *,
    side: str,
    qty: float,
    mid: float,
    bbo: BboQuote,
    fee_rate: float = 0.001,
    extra_slip_rate: float = 0.0002,
) -> dict[str, Any]:
    """
    Supuestos equivalentes (contrato cost_contract_v1):
    - mismo fee, mismo extra_slip
    - V1_proxy: mid + 0 proxy_spread + slip+fee (sin BBO touch)
    - V2_touch: ask/bid + mismo slip+fee
    Diferencia ≈ valor del touch BBO vs mid (más slip/fee sobre bases distintas).
    """
    fee = D(fee_rate)
    slip = D(extra_slip_rate)
    q = D(qty)
    m = D(mid)
    side_u = side.upper()
    if side_u == "BUY":
        c1 = buy_all_in(
            mid=m,
            ask=None,
            qty=q,
            fee_rate=fee,
            extra_slip_rate=slip,
            use_observed_ask=False,
            proxy_half_spread=D(0),
        )
        c2 = buy_all_in(
            mid=m,
            ask=D(bbo.ask_price),
            qty=q,
            fee_rate=fee,
            extra_slip_rate=slip,
            use_observed_ask=True,
        )
    else:
        c1 = sell_all_in(
            mid=m,
            bid=None,
            qty=q,
            fee_rate=fee,
            extra_slip_rate=slip,
            use_observed_bid=False,
            proxy_half_spread=D(0),
        )
        c2 = sell_all_in(
            mid=m,
            bid=D(bbo.bid_price),
            qty=q,
            fee_rate=fee,
            extra_slip_rate=slip,
            use_observed_bid=True,
        )
    px1 = float(c1.price_all_in)
    px2 = float(c2.price_all_in)
    cash1 = float(c1.cash_total)
    cash2 = float(c2.cash_total)
    if side_u == "BUY":
        # positive ⇒ V2 costs more cash (worse for buyer)
        cash_diff_adverse = cash2 - cash1
        price_diff = px2 - px1
    else:
        # positive ⇒ V1 credits more (V2 worse for seller)
        cash_diff_adverse = cash1 - cash2
        price_diff = px1 - px2
    top = bbo.ask_qty if side_u == "BUY" else bbo.bid_qty
    incomplete = qty > float(top) > 0
    return {
        "mode": "MATCHED",
        "contract_id": CONTRACT_ID,
        "comparable": True,
        "side": side_u,
        "symbol": bbo.symbol,
        "qty": qty,
        "ref_mid": mid,
        "bid": bbo.bid_price,
        "ask": bbo.ask_price,
        "spread_abs": bbo.spread_abs,
        "spread_bps": float(bps(D(bbo.spread_abs), D(mid)) or 0),
        "v1_price_all_in": px1,
        "v2_price_all_in": px2,
        "price_diff_v2_minus_v1_signed": float(px2 - px1),
        "price_diff_adverse_signed": price_diff,
        "cash_v1": cash1,
        "cash_v2": cash2,
        "cash_diff_adverse_usdt": cash_diff_adverse,
        "diff_bps_vs_mid": float(bps(D(px2 - px1), D(mid)) or 0),
        "fee_rate": fee_rate,
        "extra_slip_rate": extra_slip_rate,
        "v1_components": components_to_dict(c1),
        "v2_components": components_to_dict(c2),
        "top_qty_visible": top,
        "cover_pct": min(1.0, float(top) / qty) if qty > 0 else None,
        "incomplete_without_l2": incomplete,
        "cause": (
            "matched_fee_slip; difference ≈ mid→touch observed BBO "
            "(+ compounding on fee/slip bases)"
        ),
        "param_note": {
            "v1": "mid + 0 proxy_spread + matched slip/fee",
            "v2": "ask/bid + matched slip/fee",
            "isolates": "observed_touch_vs_mid",
        },
        "hypothesis_label": "HYPOTHETICAL_NOT_A_FILL",
    }


def _pack_row(
    *,
    mode: str,
    side: str,
    qty: float,
    mid: float,
    bbo: BboQuote,
    v1_fill: dict,
    v2_fill: dict,
    param_note: dict,
) -> dict[str, Any]:
    if not v1_fill.get("ok") or not v2_fill.get("ok"):
        return {
            "mode": mode,
            "comparable": False,
            "reason": v2_fill.get("reason") or v1_fill.get("reason"),
            "v1": v1_fill,
            "v2": v2_fill,
            "param_note": param_note,
        }
    px1 = float(v1_fill["price"])
    px2 = float(v2_fill["price_all_in"])
    fq = float(v2_fill.get("fill_qty") or qty)
    side_u = side.upper()
    cash1 = px1 * fq
    cash2 = px2 * fq
    if side_u == "BUY":
        cash_diff_adverse = cash2 - cash1
        price_adverse = px2 - px1
    else:
        cash_diff_adverse = cash1 - cash2
        price_adverse = px1 - px2
    top = bbo.ask_qty if side_u == "BUY" else bbo.bid_qty
    return {
        "mode": mode,
        "comparable": True,
        "side": side_u,
        "symbol": bbo.symbol,
        "qty": qty,
        "ref_mid": mid,
        "bid": bbo.bid_price,
        "ask": bbo.ask_price,
        "spread_abs": bbo.spread_abs,
        "spread_bps": float(bps(D(bbo.spread_abs), D(mid)) or 0),
        "v1_price_all_in": px1,
        "v2_price_all_in": px2,
        "price_diff_v2_minus_v1_signed": px2 - px1,
        "price_diff_adverse_signed": price_adverse,
        "cash_v1": cash1,
        "cash_v2": cash2,
        "cash_diff_adverse_usdt": cash_diff_adverse,
        "diff_bps_vs_mid": float(bps(D(px2 - px1), D(mid)) or 0),
        "v1_slip_component": v1_fill.get("slip_component"),
        "v1_spread_component": v1_fill.get("spread_component"),
        "v1_fee_component": v1_fill.get("fee_component"),
        "v2_fee_total": v2_fill.get("fee_total"),
        "v2_slip_total": v2_fill.get("slip_total"),
        "top_qty_visible": top,
        "cover_pct": min(1.0, float(top) / qty) if qty > 0 else None,
        "incomplete_without_l2": bool(v2_fill.get("partial")) or (qty > float(top) > 0),
        "partial": v2_fill.get("partial"),
        "cause": "legacy_param_mismatch_dominates_unless_matched",
        "param_note": param_note,
        "hypothesis_label": "HYPOTHETICAL_NOT_A_FILL",
    }


def run_fair_analysis(
    events: list[dict[str, Any]],
    *,
    sizes: tuple[SizeScenario, ...] = DEFAULT_SIZES,
    bucket_ms: int = 30_000,
) -> dict[str, Any]:
    """Una muestra por (symbol, bucket); filas = side×size — NO independientes."""
    buckets = subsample_by_bucket(events, bucket_ms=bucket_ms)
    independence = {
        "n_events_raw": len(events),
        "n_symbol_time_buckets": len(buckets),
        "bucket_ms": bucket_ms,
        "note": (
            "60 buckets AM = symbol×time cells, NOT 360 independent samples. "
            "Each bucket expands to 2 sides × 3 sizes = 6 derived rows (correlated)."
        ),
        "derived_rows_per_bucket": 2 * len(sizes),
        "cross_asset_correlation": "BTC/ETH/SOL buckets at same wall clock are contemporaneous",
        "do_not_use_for_naive_ci": True,
    }

    legacy_rows: list[dict] = []
    matched_rows: list[dict] = []

    for ev in buckets:
        bbo = _quote_from_event(ev)
        if bbo is None:
            continue
        now = int(ev.get("captured_at_ms") or bbo.received_at_ms)
        mid = bbo.mid
        for side in ("BUY", "SELL"):
            for sc in sizes:
                qty = qty_from_notional(sc.notional_usdt, mid)
                if not qty:
                    continue
                leg = evaluate_legacy(side=side, qty=qty, mid=mid, bbo=bbo, now_ms=now)
                leg["size_label"] = sc.label
                leg["notional_usdt"] = sc.notional_usdt
                leg["bucket_key"] = f"{bbo.symbol}:{bbo.received_at_ms // bucket_ms}"
                legacy_rows.append(leg)
                mat = evaluate_matched(side=side, qty=qty, mid=mid, bbo=bbo)
                mat["size_label"] = sc.label
                mat["notional_usdt"] = sc.notional_usdt
                mat["bucket_key"] = leg["bucket_key"]
                matched_rows.append(mat)

    return {
        "contract": CONTRACT_SPEC,
        "independence": independence,
        "legacy": _summarize(legacy_rows, mode="LEGACY"),
        "matched": _summarize(matched_rows, mode="MATCHED"),
        "labels": {
            "observed": "BBO",
            "hypothetical": "decisions",
            "estimated_fill": "sim",
            "paper_or_real": "NONE",
        },
    }


def _summarize(rows: list[dict], *, mode: str) -> dict[str, Any]:
    comp = [r for r in rows if r.get("comparable")]
    by_group: dict[str, list] = defaultdict(list)
    for r in comp:
        key = f"{r.get('symbol')}|{r.get('side')}"
        by_group[key].append(r)

    groups = {}
    for key, rs in sorted(by_group.items()):
        diffs_bps = [float(r["diff_bps_vs_mid"]) for r in rs]
        cash = [float(r["cash_diff_adverse_usdt"]) for r in rs]
        spreads_bps = [float(r["spread_bps"]) for r in rs]
        incomplete = sum(1 for r in rs if r.get("incomplete_without_l2"))
        groups[key] = {
            "n_derived_rows": len(rs),
            "n_unique_buckets": len({r.get("bucket_key") for r in rs}),
            "diff_bps": _pctiles(diffs_bps),
            "cash_diff_adverse_usdt": _pctiles(cash),
            "spread_bps": _pctiles(spreads_bps),
            "n_incomplete_l2": incomplete,
            "sample": [
                {
                    "size_label": r.get("size_label"),
                    "ref_mid": r.get("ref_mid"),
                    "spread_abs": r.get("spread_abs"),
                    "v1": r.get("v1_price_all_in"),
                    "v2": r.get("v2_price_all_in"),
                    "diff_bps": r.get("diff_bps_vs_mid"),
                    "cash_adverse": r.get("cash_diff_adverse_usdt"),
                    "cause": r.get("cause"),
                }
                for r in rs[:2]
            ],
        }

    by_size = {}
    for sc in DEFAULT_SIZES:
        sub = [r for r in comp if r.get("size_label") == sc.label]
        by_size[sc.label] = {
            "n": len(sub),
            "notional_usdt": sc.notional_usdt,
            "median_diff_bps": (
                float(statistics.median([float(r["diff_bps_vs_mid"]) for r in sub]))
                if sub
                else None
            ),
            "median_cash_adverse": (
                float(statistics.median([float(r["cash_diff_adverse_usdt"]) for r in sub]))
                if sub
                else None
            ),
            "n_incomplete_l2": sum(1 for r in sub if r.get("incomplete_without_l2")),
        }

    # Notional-weighted aggregate (document methodology)
    w_bps = []
    w_cash = []
    for r in comp:
        n = float(r.get("notional_usdt") or 0)
        if n <= 0:
            continue
        w_bps.append((float(r["diff_bps_vs_mid"]), n))
        w_cash.append((float(r["cash_diff_adverse_usdt"]), n))

    def wavg(pairs: list[tuple[float, float]]) -> float | None:
        if not pairs:
            return None
        s = sum(v * w for v, w in pairs)
        tw = sum(w for _, w in pairs)
        return s / tw if tw else None

    return {
        "mode": mode,
        "n_derived_rows": len(rows),
        "n_comparable": len(comp),
        "n_not_comparable": len(rows) - len(comp),
        "by_symbol_side": groups,
        "by_size": by_size,
        "notional_weighted": {
            "mean_diff_bps": wavg(w_bps),
            "mean_cash_adverse_usdt": wavg(w_cash),
            "methodology": "weight each derived row by scenario notional_usdt; "
            "still correlated within bucket — not for CI",
        },
        "warning": (
            "Do not interpret BUY+SELL pooled median as engine equivalence. "
            "Report per symbol|side groups."
        ),
    }
