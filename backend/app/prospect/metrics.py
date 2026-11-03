"""Prospective evaluation metrics — SHADOW_LIVE only unless explicitly filtered."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from ..ml.metrics_audit import block_bootstrap_ci


def prospective_metrics(
    execute: Callable, *, experiment_type: str = "SHADOW_LIVE"
) -> dict[str, Any]:
    rows = list(
        execute(
            """SELECT d.action, d.symbol, d.observed_price, d.estimated_costs_json,
                      o.observed_net_return, o.observed_label, o.status AS outcome_status,
                      o.data_quality, d.resolution_status
               FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               LEFT JOIN prospect_outcomes o ON o.decision_id=d.id
               WHERE e.experiment_type=%s""",
            (experiment_type,),
        )
    )
    pending = sum(1 for r in rows if r["resolution_status"] == "PENDING")
    resolved = [r for r in rows if r["resolution_status"] == "RESOLVED"]
    invalid = sum(1 for r in rows if r["resolution_status"] == "INVALID")

    buys = [r for r in resolved if r["action"] == "BUY"]
    holds = [r for r in resolved if r["action"] == "HOLD"]
    buy_nets = [
        float(r["observed_net_return"])
        for r in buys
        if r["observed_net_return"] is not None
    ]
    # Classification only where label exists (BUY decisions with observed_label)
    labeled = [
        r
        for r in buys
        if r.get("observed_label") is not None and r.get("estimated_costs_json") is not None
    ]
    # We don't store probability on prospect decisions for SMA strategy — report N/A
    classification = {
        "n_buy_labeled": len([r for r in buys if r.get("observed_label") is not None]),
        "note": "SMA prospect signals are discrete BUY/HOLD; probability metrics apply to ML Shadow predictions separately.",
    }

    # Hypothetical per-signal return: BUY only (HOLD is NOT a profitable trade)
    hypo = {
        "n_buy": len(buys),
        "n_hold": len(holds),
        "mean_buy_net": float(np.mean(buy_nets)) if buy_nets else None,
        "buy_net_ci": block_bootstrap_ci(buy_nets) if len(buy_nets) >= 2 else {
            "mean": float(np.mean(buy_nets)) if buy_nets else None,
            "low": None,
            "high": None,
            "n": len(buy_nets),
            "warning": "insufficient_sample",
        },
        "hold_counted_as_trade": False,
    }

    # Simple executable virtual portfolio: equal notional on each BUY, cash otherwise
    # Using observed_net_return as fraction on that trade only (not compounded portfolio path)
    portfolio = {
        "unit": "mean_buy_signal_fraction_not_compounded_equity",
        "sum_buy_nets": float(sum(buy_nets)) if buy_nets else 0.0,
        "vs_cash": (float(np.mean(buy_nets)) if buy_nets else 0.0) - 0.0,
        "insufficient_for_edge_claim": len(buy_nets) < 30,
        "warning": (
            "Sample too small for robust edge claim."
            if len(buy_nets) < 30
            else "Still require pre-registered success criteria before PAPER_AI."
        ),
    }

    by_symbol: dict[str, Any] = {}
    for r in resolved:
        sym = r["symbol"]
        by_symbol.setdefault(sym, {"BUY": 0, "HOLD": 0, "buy_nets": []})
        by_symbol[sym][r["action"]] = by_symbol[sym].get(r["action"], 0) + 1
        if r["action"] == "BUY" and r["observed_net_return"] is not None:
            by_symbol[sym]["buy_nets"].append(float(r["observed_net_return"]))
    symbol_rows = []
    for sym, v in sorted(by_symbol.items()):
        nets = v["buy_nets"]
        symbol_rows.append(
            {
                "symbol": sym,
                "buys": v.get("BUY", 0),
                "holds": v.get("HOLD", 0),
                "mean_buy_net": float(np.mean(nets)) if nets else None,
            }
        )

    # Simple path drawdown on cumulative BUY nets (research only)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for n in buy_nets:
        cum += n
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)

    return {
        "experiment_type": experiment_type,
        "counts": {
            "pending": pending,
            "resolved": len(resolved),
            "invalid": invalid,
            "total": len(rows),
        },
        "classification": classification,
        "probability_quality": {
            "applicable": False,
            "note": "SMA discrete signals; ECE/Brier live in /api/ml/metrics-audit for ML shadow.",
        },
        "hypothetical_signals": hypo,
        "virtual_portfolio": {
            **portfolio,
            "max_drawdown_cum_buy_nets": float(max_dd),
            "exposure_buy_share": (len(buys) / len(resolved)) if resolved else None,
            "rejected_or_blocked_note": "Breaker HOLDs are not executable trades; see decision reasons.",
        },
        "benchmarks": {
            "cash_net": 0.0,
            "sma_paper": "incompatible_period_unless_aligned — use overview separately",
            "buy_and_hold": "requires aligned entry/exit window; not auto-compared here",
            "note": "SMA/buy-hold portfolio comparisons require aligned periods; see /api/ml/research/latest for backtests. Do not mix with SHADOW_LIVE until n sufficient.",
        },
        "by_symbol": symbol_rows,
        "costs_assumed": {
            "fee_rate": 0.001,
            "slip_rate": 0.001,
            "embedded_in_net_forward_return": True,
        },
        "separated_from_shadow_replay": True,
        "hold_counted_as_profitable_trade": False,
    }
