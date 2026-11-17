"""Reconciliación decimal de costos D28H5 (artefacto AC) — sin re-optimizar ni mutar freeze."""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

from ..research.etapa_z import FEE_RATE, SLIP_RATE, SPREAD_BPS

# Motor research: cost = |notional| * (fee + slip + spread_bps/20000)
COST_FRAC = FEE_RATE + SLIP_RATE + (SPREAD_BPS / 20_000.0)
FEE_SHARE = FEE_RATE / COST_FRAC if COST_FRAC else 0.0
SLIP_SHARE = SLIP_RATE / COST_FRAC if COST_FRAC else 0.0
SPREAD_SHARE = (SPREAD_BPS / 20_000.0) / COST_FRAC if COST_FRAC else 0.0

D = Decimal


def _d(x: Any) -> Decimal:
    return D(str(x))


def _q(x: Decimal, places: str = "0.000001") -> Decimal:
    return x.quantize(D(places), rounding=ROUND_HALF_EVEN)


def reconcile_d28h5_costs_from_artifact(
    artifact_path: str | Path | None = None,
) -> dict[str, Any]:
    """Lee etapa_ac_results.json y reconcilia split fee/slip/spread vs notional."""
    root = Path(__file__).resolve().parents[3]
    path = Path(artifact_path) if artifact_path else root / "data" / "market_history" / "etapa_ac_results.json"
    if not path.exists():
        return {"ok": False, "reason": "artifact_missing", "path": str(path)}

    data = json.loads(path.read_text(encoding="utf-8"))
    economic = (data.get("economic") or {}).get("reconcile") or {}
    costs = economic.get("costs") or {}
    activity = economic.get("activity") or {}

    total = _d(costs.get("total") or 0)
    fee = _d(costs.get("fee") or 0)
    slip = _d(costs.get("slip") or 0)
    spread = _d(costs.get("spread") or 0)
    split_sum = fee + slip + spread
    notional = _d(activity.get("notional_traded") or 0)

    implied_notional = total / _d(COST_FRAC) if COST_FRAC else D(0)
    fee_from_notional = notional * _d(FEE_RATE)
    slip_from_notional = notional * _d(SLIP_RATE)
    spread_from_notional = notional * _d(SPREAD_BPS) / D(20000)

    return {
        "ok": True,
        "config_hash": data.get("config_hash"),
        "hash_expected": "5326edb8a539cfe5",
        "hash_match": data.get("config_hash") == "5326edb8a539cfe5",
        "frozen_params": {
            "fee_rate": FEE_RATE,
            "slip_rate": SLIP_RATE,
            "spread_bps": SPREAD_BPS,
            "cost_frac": COST_FRAC,
            "unchanged": True,
        },
        "reported": {
            "total": str(_q(total)),
            "fee": str(_q(fee)),
            "slip": str(_q(slip)),
            "spread": str(_q(spread)),
            "split_sum": str(_q(split_sum)),
            "split_residual": str(_q(total - split_sum)),
            "notional_traded": str(_q(notional, "0.0001")),
            "rebalances_real": activity.get("rebalances_real"),
            "turnover_events": activity.get("turnover_events"),
            "buys": activity.get("buys"),
            "sells": activity.get("sells"),
        },
        "identity_checks": {
            "split_sums_to_total": abs(total - split_sum) < D("0.00001"),
            "notional_times_cost_frac": str(_q(notional * _d(COST_FRAC))),
            "vs_reported_total_abs_delta": str(_q(abs(notional * _d(COST_FRAC) - total))),
            "fee_share_ok": abs(fee - fee_from_notional) < D("0.01"),
            "slip_share_ok": abs(slip - slip_from_notional) < D("0.01"),
            "spread_share_ok": abs(spread - spread_from_notional) < D("0.01"),
            "implied_notional_from_total": str(_q(implied_notional, "0.0001")),
        },
        "explanation": (
            "Los ~72.733833 USDT son fricciones del motor research V1: "
            "|notional|×(fee 10bps + slip 5bps + spread_proxy 0.5bps). "
            "No es fee de exchange real aislada; incluye slip y spread proxy al close. "
            "Holdout AA consumido — no revalidar como prueba independiente."
        ),
        "v1_vs_v2_note": (
            "V2 con BBO real puede aumentar costos (compra ask / venta bid) o "
            "rechazar por stale; no recalibra D28H5 ni altera parámetros congelados."
        ),
        "holdout_consumed": bool(economic.get("holdout_consumed")),
        "prospect": economic.get("prospect"),
        "path": str(path),
    }
