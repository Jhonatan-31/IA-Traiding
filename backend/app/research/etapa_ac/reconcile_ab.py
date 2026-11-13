"""Reconciliación decimal de atribución/costos AB (holdout consumido — no nueva prueba)."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any


def D(x: Any) -> Decimal:
    return Decimal(str(x))


def load_ab(*cands: str) -> dict[str, Any]:
    for c in cands:
        p = Path(c)
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError("etapa_ab_results.json")


def reconcile_ab_economics(ab: dict[str, Any] | None = None) -> dict[str, Any]:
    ab = ab or load_ab(
        "/artifacts/history/etapa_ab_results.json",
        "data/market_history/etapa_ab_results.json",
    )
    suite = ab["suite"]
    d28 = D(suite["D28H5"]["net_vs_initial"])
    bh = D(suite["Z-BH-EQ"]["net_vs_initial"])
    em = D(suite["EXP-MATCH-EQ"]["net_vs_initial"])
    f55 = D(suite["FIXED-55-EQ"]["net_vs_initial"])
    cash = D(suite["CASH"]["net_vs_initial"])
    fees = D(suite["D28H5"]["fees_and_frictions"])
    split = suite["D28H5"].get("cost_split") or {}
    fee, slip, spread = D(split.get("fee", 0)), D(split.get("slip", 0)), D(split.get("spread", 0))

    market = bh - cash
    exp_eff = em - bh
    active = d28 - em
    suma = market + exp_eff + active
    residual = d28 - suma
    split_sum = fee + slip + spread

    d = suite["D28H5"]
    return {
        "ok": residual == 0 and abs(fees - split_sum) <= Decimal("0.00001"),
        "pl": {
            "d28h5": str(d28),
            "bh_eq": str(bh),
            "exp_match": str(em),
            "fixed55": str(f55),
            "cash": str(cash),
            "vs_bh_eq": str(d28 - bh),
            "vs_fixed55": str(d28 - f55),
            "vs_cash": str(d28 - cash),
            "vs_exp_match": str(d28 - em),
        },
        "attribution": {
            "market_full_bh_eq": str(market),
            "exposure_reduction_descriptive": str(exp_eff),
            "active_vs_exp_match": str(active),
            "sum": str(suma),
            "residual": str(residual),
            "identity": "d28 = market + exposure_effect + active  (vs cash baseline)",
            "costs_in_nets": True,
            "note": "Todos los P/L son netos de fricciones del motor; no restar costos otra vez",
        },
        "costs": {
            "total": str(fees),
            "fee": str(fee),
            "slip": str(slip),
            "spread": str(spread),
            "split_sum": str(split_sum),
            "split_residual": str(fees - split_sum),
            "gross_approx_net_plus_costs": str(d28 + fees),
        },
        "activity": {
            "rebalances_real": d.get("rebalances_real"),
            "turnover_events": d.get("turnover_events"),
            "buys": d.get("buys"),
            "sells": d.get("sells"),
            "signal_changes": d.get("signal_changes"),
            "notional_traded": d.get("notional_traded"),
            "cost_per_rebalance": d.get("cost_per_rebalance"),
            "definitions": {
                "rebalances_real": "días con ≥1 ajuste |delta|≥1 USDT",
                "turnover_events": "ajustes individuales por símbolo (no round-trips)",
                "buys_sells": "conteo de lados en esos ajustes",
            },
        },
        "risk": {
            "dd_d28": d.get("max_drawdown"),
            "dd_bh": suite["Z-BH-EQ"].get("max_drawdown"),
            "dd_f55": suite["FIXED-55-EQ"].get("max_drawdown"),
            "exp_d28": d.get("avg_exposure"),
            "exp_f55": suite["FIXED-55-EQ"].get("avg_exposure"),
            "cash_days": d.get("cash_days"),
        },
        "prospect": {
            "status": (ab.get("prospect") or {}).get("status"),
            "enabled": (ab.get("prospect") or {}).get("enabled"),
            "hash": ab.get("config_hash"),
        },
        "holdout_consumed": True,
        "economic_verdict_ac": "POSIBLE VENTAJA INCREMENTAL, SIN VALIDAR",
        "rationale": (
            "Supera FIXED-55 causal (~+90.75) y EXP-MATCH (~+92.83) pero pierde vs efectivo; "
            "holdout AA consumido; sin observación prospectiva activa."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(reconcile_ab_economics(), indent=2))
