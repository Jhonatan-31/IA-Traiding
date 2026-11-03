"""Prospective results report — SHADOW_LIVE only; never invents outcomes."""
from __future__ import annotations

import json
import math
from typing import Any, Callable

import numpy as np

from .metrics import prospective_metrics


def _costs(row: dict) -> dict:
    c = row.get("estimated_costs_json") or {}
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except Exception:
            c = {}
    return c if isinstance(c, dict) else {}


def _result(row: dict) -> dict:
    r = row.get("result_json") or {}
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except Exception:
            r = {}
    return r if isinstance(r, dict) else {}


def _prob(row: dict) -> float | None:
    """SMA prospect has no calibrated probability — may appear in system_state later."""
    ss = row.get("system_state_json") or {}
    if isinstance(ss, str):
        try:
            ss = json.loads(ss)
        except Exception:
            ss = {}
    if isinstance(ss, dict) and ss.get("probability") is not None:
        try:
            return float(ss["probability"])
        except (TypeError, ValueError):
            return None
    return None


def decision_result_rows(
    execute: Callable, *, experiment_type: str = "SHADOW_LIVE", limit: int = 200
) -> list[dict[str, Any]]:
    rows = list(
        execute(
            """SELECT d.id, d.created_at, d.decision_ts, d.symbol, d.interval, d.action,
                      d.reason, d.observed_price, d.estimated_costs_json, d.system_state_json,
                      d.candle_open_ms, d.horizon_bars, d.resolution_status,
                      o.status AS outcome_status, o.observed_net_return, o.observed_label,
                      o.data_quality, o.result_json, o.resolved_at, e.experiment_type
               FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               LEFT JOIN prospect_outcomes o ON o.decision_id=d.id
               WHERE e.experiment_type=%s
               ORDER BY d.id ASC
               LIMIT %s""",
            (experiment_type, limit),
        )
    )
    out = []
    for r in rows:
        costs = _costs(r)
        res = _result(r)
        entry = res.get("entry_close")
        exit_px = res.get("exit_close")
        if entry is None:
            entry = r.get("observed_price")
        asset_ret = None
        if entry is not None and exit_px is not None and float(entry) > 0:
            asset_ret = (float(exit_px) - float(entry)) / float(entry)
        hypo_net = None
        class_hit = None
        if r["action"] == "BUY" and r.get("resolution_status") == "RESOLVED":
            hypo_net = r.get("observed_net_return")
            if r.get("observed_label") is not None:
                class_hit = bool(int(r["observed_label"]) == 1)
        elif r["action"] == "HOLD" and r.get("resolution_status") == "RESOLVED":
            hypo_net = None  # HOLD is not an executable winning trade
            class_hit = None
        out.append(
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "signal_ts": r["decision_ts"],
                "created_at": r["created_at"],
                "action": r["action"],
                "reason": r["reason"],
                "probability": _prob(r),
                "probability_note": "N/A — señales SMA discretas sin probabilidad calibrada"
                if _prob(r) is None
                else None,
                "entry_price_observed": float(entry) if entry is not None else None,
                "exit_price_observed": float(exit_px) if exit_px is not None else None,
                "asset_return": asset_ret,
                "estimated_costs": {
                    "fee_rate": costs.get("fee_rate"),
                    "slip_rate": costs.get("slip_rate"),
                    "spread_bps": costs.get("spread_bps"),
                },
                "hypothetical_net_if_buy": hypo_net,
                "hold_counted_as_trade": False,
                "classification_hit": class_hit,
                "data_quality": r.get("data_quality") or res.get("data_quality"),
                "resolution_status": r["resolution_status"],
                "outcome_status": r.get("outcome_status"),
                "resolved_at": r.get("resolved_at"),
                "candle_open_ms": r.get("candle_open_ms"),
                "horizon_bars": r.get("horizon_bars"),
                "experiment_type": r["experiment_type"],
                "result_class": "hypothetical_signal"
                if r["action"] == "BUY"
                else "abstention_hold",
                "executed_trade": False,
                "note": "Outcome separado de decisión inmutable; no es operación en cartera SMA.",
            }
        )
    return out


def _safe_brier(probs: list[float], labels: list[int]) -> float | None:
    if len(probs) < 2 or len(probs) != len(labels):
        return None
    return float(np.mean([(p - y) ** 2 for p, y in zip(probs, labels)]))


def _safe_logloss(probs: list[float], labels: list[int]) -> float | None:
    if len(probs) < 2 or len(probs) != len(labels):
        return None
    eps = 1e-15
    ll = []
    for p, y in zip(probs, labels):
        p = min(max(float(p), eps), 1 - eps)
        ll.append(-(y * math.log(p) + (1 - y) * math.log(1 - p)))
    return float(np.mean(ll))


def prospective_report(
    execute: Callable, *, experiment_type: str = "SHADOW_LIVE"
) -> dict[str, Any]:
    rows = decision_result_rows(execute, experiment_type=experiment_type)
    metrics = prospective_metrics(execute, experiment_type=experiment_type)
    resolved = [r for r in rows if r["resolution_status"] == "RESOLVED"]
    buys = [r for r in resolved if r["action"] == "BUY"]
    holds = [r for r in resolved if r["action"] == "HOLD"]
    pending = [r for r in rows if r["resolution_status"] == "PENDING"]
    invalid = [r for r in rows if r["resolution_status"] == "INVALID"]

    # Directional accuracy on BUY only (label 1 = net>0 after costs)
    buy_labels = [1 if r["classification_hit"] else 0 for r in buys if r["classification_hit"] is not None]
    accuracy = float(np.mean(buy_labels)) if buy_labels else None

    probs = [r["probability"] for r in buys if r["probability"] is not None]
    labels_for_prob = [
        1 if r["classification_hit"] else 0
        for r in buys
        if r["probability"] is not None and r["classification_hit"] is not None
    ]
    brier = _safe_brier(probs, labels_for_prob) if probs and labels_for_prob else None
    logloss = _safe_logloss(probs, labels_for_prob) if probs and labels_for_prob else None

    buy_nets = [
        float(r["hypothetical_net_if_buy"])
        for r in buys
        if r["hypothetical_net_if_buy"] is not None
    ]
    # Equity curve of cumulative hypothetical BUY nets (not a funded portfolio)
    curve = []
    cum = 0.0
    for r in buys:
        if r["hypothetical_net_if_buy"] is None:
            continue
        cum += float(r["hypothetical_net_if_buy"])
        curve.append(
            {
                "t": r["resolved_at"] or r["signal_ts"],
                "symbol": r["symbol"],
                "cum_hypo_buy_net": cum,
                "decision_id": r["id"],
            }
        )

    sufficient = len(buy_nets) >= 30
    return {
        "experiment_type": experiment_type,
        "evidence_label": "Evidencia insuficiente" if not sufficient else "Muestra mínima",
        "sample_sufficient": sufficient,
        "counts": {
            "total": len(rows),
            "pending": len(pending),
            "resolved": len(resolved),
            "invalid": len(invalid),
            "buy_resolved": len(buys),
            "hold_resolved": len(holds),
            "abstentions_hold": len(holds),
        },
        "classification": {
            "accuracy_buy_directional": accuracy,
            "n": len(buy_labels),
            "note": "Accuracy solo sobre BUY resueltas (net>0). HOLD no cuenta como acierto rentable.",
        },
        "probability_scores": {
            "brier": brier,
            "logloss": logloss,
            "applicable": brier is not None,
            "note": "N/A sin probabilidades calibradas (SMA discreto).",
        },
        "hypothetical_buy": {
            "n": len(buy_nets),
            "mean_net": float(np.mean(buy_nets)) if buy_nets else None,
            "sum_net": float(sum(buy_nets)) if buy_nets else 0.0,
            "vs_cash": (float(np.mean(buy_nets)) if buy_nets else 0.0) - 0.0,
            "hold_counted_as_trade": False,
        },
        "costs_aggregate": metrics.get("costs_assumed"),
        "by_symbol": metrics.get("by_symbol"),
        "equity_curve_hypo_buy": curve,
        "show_portfolio_pnl": False,
        "portfolio_pnl_note": (
            "No se muestra rentabilidad de cartera: no hay simulación de ejecución "
            "con asignación de capital válida en este informe."
        ),
        "decisions": rows,
        "metrics": metrics,
        "separated_from": ["SHADOW_REPLAY", "BACKTEST", "PAPER_TRADE", "SMA_paper_account"],
    }
