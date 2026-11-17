"""AM6 — reconciliación exacta fee / spread / slip sin doble conteo."""
from __future__ import annotations

from typing import Any

from ..prospect.execution import ExecutionAssumptions, estimate_fill_price
from .bbo_store import BboQuote
from .engine_v2 import ExecutionV2Assumptions, simulate_fill_v2


def reconstruct_al_anomaly_buy(
    *,
    mid: float = 64018.225000000006,
    ask: float = 64018.23,
    bid: float = 64018.22,
    ask_qty: float = 0.9307,
    bid_qty: float = 3.37006,
    qty: float = 0.001,
) -> dict[str, Any]:
    """Reconstruye la comparación AL con fórmulas explícitas (no inventa timestamps)."""
    v1_a = ExecutionAssumptions()  # fee=0.001, slip=0.001, spread_bps=2
    v2_a = ExecutionV2Assumptions()  # fee=0.001, extra_slip=0.0002
    half_spread = mid * (v1_a.spread_bps / 10000.0)
    slip_v1 = mid * v1_a.base_slip_rate
    raw_v1 = mid + half_spread + slip_v1
    px_v1 = raw_v1 * (1.0 + v1_a.fee_rate)
    raw_v2 = ask * (1.0 + v2_a.extra_slip_rate)
    px_v2 = raw_v2 * (1.0 + v2_a.fee_rate)
    # Matched assumptions: same fee, V1 slip/spread zeroed → isolate BBO vs mid
    v1_matched = ExecutionAssumptions(fee_rate=0.001, base_slip_rate=0.0, spread_bps=0.0)
    px_v1_matched = estimate_fill_price(
        side="BUY", mid_or_ref=mid, assumptions=v1_matched, order_qty=qty
    )["price"]
    bbo = BboQuote(
        symbol="BTCUSDT",
        bid_price=bid,
        bid_qty=bid_qty,
        ask_price=ask,
        ask_qty=ask_qty,
        received_at_ms=0,
    )
    v2_fill = simulate_fill_v2(
        side="BUY", qty=qty, ref_mid=mid, bbo=bbo, assumptions=v2_a, now_ms=0
    )
    return {
        "status": "RECONSTRUCTED_FROM_AL_NUMBERS",
        "auditable_original_timestamps": False,
        "original_verdict": "NO_AUDITABLE_AS_MARKET_MOVE — model assumption mismatch",
        "inputs": {
            "mid": mid,
            "ask": ask,
            "bid": bid,
            "qty": qty,
            "v1_defaults": {
                "fee_rate": v1_a.fee_rate,
                "base_slip_rate": v1_a.base_slip_rate,
                "spread_bps": v1_a.spread_bps,
            },
            "v2_defaults": {
                "fee_rate": v2_a.fee_rate,
                "extra_slip_rate": v2_a.extra_slip_rate,
            },
        },
        "formulas": {
            "v1_buy": "px = (mid + mid*spread_bps/10000 + mid*base_slip) * (1+fee)",
            "v2_buy": "px = (ask * (1+extra_slip)) * (1+fee)",
            "note": "V1 half-spread+slip are proxies; V2 ask already embeds half-spread vs mid",
        },
        "v1": {
            "half_spread": half_spread,
            "slip": slip_v1,
            "raw": raw_v1,
            "price_all_in": px_v1,
            "cash_buy": px_v1 * qty,
        },
        "v2": {
            "executable_ask": ask,
            "half_spread_vs_mid": ask - mid,
            "extra_slip_abs": raw_v2 - ask,
            "raw": raw_v2,
            "price_all_in": px_v2,
            "cash_buy": px_v2 * qty,
            "engine": v2_fill,
        },
        "diff_unit_v2_minus_v1": px_v2 - px_v1,
        "diff_cash_v2_minus_v1": (px_v2 - px_v1) * qty,
        "decomposition": {
            "v1_proxy_friction_bps_approx": (
                (half_spread + slip_v1) / mid * 10000.0 + v1_a.fee_rate * 10000.0
            ),
            "v2_friction_bps_approx": (
                ((ask - mid) + (raw_v2 - ask)) / mid * 10000.0 + v2_a.fee_rate * 10000.0
            ),
            "primary_cause": (
                "V1 default base_slip_rate=0.001 (10 bps) + spread_bps=2 dwarfs "
                "V2 extra_slip_rate=0.0002 (2 bps) on a near-zero live spread; "
                "not evidence that V2 is economically superior."
            ),
        },
        "matched_assumptions_sensitivity": {
            "v1_fee_only_price": px_v1_matched,
            "v2_all_in": px_v2,
            "diff_v2_minus_v1_fee_aligned": px_v2 - float(px_v1_matched),
            "label": "analysis_only_not_production_defaults",
        },
    }


def decompose_pair_costs(
    *,
    side: str,
    qty: float,
    ref_mid: float,
    bbo: BboQuote,
    v1: ExecutionAssumptions | None = None,
    v2: ExecutionV2Assumptions | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Separación fee/spread/slip; no doble conteo de spread en narrativa."""
    v1_a = v1 or ExecutionAssumptions()
    v2_a = v2 or ExecutionV2Assumptions()
    v1_fill = estimate_fill_price(
        side=side, mid_or_ref=ref_mid, assumptions=v1_a, order_qty=qty
    )
    v2_fill = simulate_fill_v2(
        side=side, qty=qty, ref_mid=ref_mid, bbo=bbo, assumptions=v2_a, now_ms=now_ms
    )
    if not v1_fill.get("ok") or not v2_fill.get("ok"):
        return {
            "ok": False,
            "v1": v1_fill,
            "v2": v2_fill,
            "reason": "fill_failed",
        }
    fq = float(v2_fill["fill_qty"])
    px1 = float(v1_fill["price"])
    px2 = float(v2_fill["price_all_in"])
    side_u = side.upper()
    if side_u == "BUY":
        cash_v1 = px1 * fq
        cash_v2 = px2 * fq
        cash_diff = cash_v2 - cash_v1  # >0 ⇒ V2 requires more cash
    else:
        cash_v1 = px1 * fq
        cash_v2 = px2 * fq
        cash_diff = cash_v1 - cash_v2  # >0 ⇒ V1 credits more
    return {
        "ok": True,
        "side": side_u,
        "qty_fill": fq,
        "ref_mid": ref_mid,
        "v1_price_all_in": px1,
        "v2_price_all_in": px2,
        "v1_components": {
            "spread_half": v1_fill.get("spread_component"),
            "slip": v1_fill.get("slip_component"),
            "fee_per_unit": v1_fill.get("fee_component"),
            "note": "spread+slip are mid proxies; fee embedded in all-in",
        },
        "v2_components": {
            "executable": v2_fill.get("executable_price"),
            "spread_abs_book": v2_fill.get("spread_abs"),
            "spread_already_in_executable": True,
            "extra_slip_total": v2_fill.get("slip_total"),
            "fee_total": v2_fill.get("fee_total"),
        },
        "cash_flow": {
            "v1": cash_v1,
            "v2": cash_v2,
            "diff_adverse_to_trader": cash_diff,
            "convention": (
                "BUY: cash outlay; SELL: cash credit; "
                "diff_adverse_to_trader>0 means V2 worse for trader vs V1 model"
            ),
        },
        "no_double_fee": True,
        "no_double_spread_in_v2_narrative": True,
    }
