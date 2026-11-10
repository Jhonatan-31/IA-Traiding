"""Centro de Investigación ampliado — cobertura histórica Etapa W."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .center_v import research_center
from .history.coverage import full_coverage_report
from .history.schema import coverage_snapshot, ensure_history_schema, files_snapshot


def research_center_w(
    execute: Callable,
    *,
    backtest_v: dict[str, Any] | None = None,
    backtest_w: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = research_center(execute, backtest_v=backtest_v)
    ensure_history_schema(execute)
    cov_files = full_coverage_report()
    try:
        db_cov = coverage_snapshot(execute)
        db_files = files_snapshot(execute)
    except Exception:
        db_cov, db_files = [], []

    oos = (backtest_w or {}).get("out_of_sample") or {}
    hold = (backtest_w or {}).get("holdout") or {}
    # enrich strategy cards with W metrics when present
    cards = base.get("strategy_cards") or []
    for c in cards:
        pid = c.get("id")
        if pid and pid in oos:
            o = oos[pid]
            c["net_oos"] = o.get("net_vs_initial")
            c["drawdown_oos"] = o.get("max_drawdown_proxy")
            c["trades_oos"] = o.get("closed_rounds")
            c["costs_oos"] = {"fees": o.get("fees"), "slip": o.get("slips")}
            c["net_holdout"] = (hold.get(pid) or {}).get("net_vs_initial")
            c["evidence"] = "Walk-forward historial Vision (Etapa W)"
            c["evaluation_period"] = (backtest_w or {}).get("span")
            st = "En investigación"
            if (o.get("buys") == 0) or (o.get("closed_rounds") or 0) == 0:
                st = "Rechazada (sin operaciones OOS)"
            elif (o.get("net_vs_initial") or 0) <= 0:
                st = "Rechazada (OOS no positivo)"
            elif (o.get("closed_rounds") or 0) < 30:
                st = "Rechazada (muestra OOS insuficiente)"
            else:
                st = "En investigación (sin promoción automática)"
            if pid in {"A_BASELINE", "B_BASELINE"}:
                st = "Baseline (inmutable)"
            if pid == "V_IA":
                st = "Solo observación"
            c["status_label"] = st

    evidence_level = "baja"
    cov_ok = 0
    for _sym, rep in (cov_files.get("by_symbol") or {}).items():
        if rep.get("verified") and (rep.get("n_bars") or 0) >= 400_000:
            cov_ok += 1
    if cov_ok >= 3:
        evidence_level = "media"  # 12m Vision verificado; aún sin garantía de edge
    if backtest_w and backtest_w.get("available"):
        bars = backtest_w.get("bars_per_symbol") or 0
        if bars >= 5_000 and cov_ok >= 3:
            evidence_level = "media-alta"
        # still not "alta" without multi-year + robustness multi-seed

    return {
        **base,
        "etapa": "W",
        "history": {
            "source": "https://data.binance.vision/",
            "docs": "https://github.com/binance/binance-public-data",
            "coverage_report": cov_files,
            "db_coverage": db_cov,
            "db_files_n": len(db_files),
            "disk": cov_files.get("disk"),
        },
        "backtest_w": {
            "available": bool(backtest_w and backtest_w.get("available")),
            "span": (backtest_w or {}).get("span"),
            "walk_forward": (backtest_w or {}).get("walk_forward"),
            "claim": (backtest_w or {}).get("claim"),
            "approval_gate": (backtest_w or {}).get("approval_gate"),
            "out_of_sample": oos,
            "holdout": hold,
            "in_sample": (backtest_w or {}).get("in_sample"),
            "b_baseline": (backtest_w or {}).get("b_baseline_full_window"),
        },
        "evidence_level": evidence_level,
        "strategy_cards": cards,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa W amplía el historial de investigación. "
            "Ninguna estrategia se declara rentable solo por más datos. "
            "A y B permanecen detenidos; sin activación nueva."
        ),
    }
