"""Payload UI Etapa X — panel «¿Cuándo tiene sentido operar?»."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .center_w import research_center_w


def _top_regimes(by_regime: dict[str, dict], *, positive: bool, limit: int = 6) -> list[dict]:
    rows = []
    for variant, segs in (by_regime or {}).items():
        for rk, s in (segs or {}).items():
            if not s.get("sufficient_n"):
                continue
            exp = s.get("expectancy")
            if exp is None:
                continue
            if positive and exp <= 0:
                continue
            if not positive and exp >= 0:
                continue
            rows.append(
                {
                    "strategy": variant,
                    "regime": rk,
                    "n": s.get("n"),
                    "expectancy_usdt": exp,
                    "net_pnl_usdt": s.get("net_pnl_sum"),
                    "win_rate": s.get("win_rate"),
                    "avg_mfe": s.get("avg_mfe"),
                    "avg_mae": s.get("avg_mae"),
                }
            )
    rows.sort(key=lambda r: abs(float(r["expectancy_usdt"] or 0)), reverse=True)
    return rows[:limit]


def research_center_x(
    execute: Callable,
    *,
    backtest_v: dict[str, Any] | None = None,
    backtest_w: dict[str, Any] | None = None,
    diagnose_x: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = research_center_w(execute, backtest_v=backtest_v, backtest_w=backtest_w)
    dx = diagnose_x or {}
    available = bool(dx.get("available"))

    when = {
        "title": "¿Cuándo tiene sentido operar?",
        "available": available,
        "evidence_level": "exploratoria" if available else "pendiente",
        "units": (dx.get("units") or {}).get("expectancy", "USDT/operación"),
        "market_history_state": dx.get("data_confirmation") or base.get("history"),
        "regime_presence": dx.get("regime_bar_counts_btc") or {},
        "losses_by_regime": _top_regimes(dx.get("by_regime") or {}, positive=False),
        "gains_by_regime_exploratory": _top_regimes(dx.get("by_regime") or {}, positive=True),
        "robust_positive": dx.get("robust_positive_segments") or [],
        "signal_quality": dx.get("signal_quality") or {},
        "hypotheses": dx.get("hypotheses_results") or [],
        "holdout_w_consumed": (dx.get("holdout_w") or {}).get("consumed", True),
        "costs_note": "Fee≈10 bps + slip≈5 bps ya en P/L neto de fills",
        "limitations": [
            "Segmentos positivos aislados pueden ser selección retrospectiva",
            "Holdout de Etapa W ya consumido — no reutilizarlo",
            "Validación independiente requiere datos posteriores a oct-2025",
            "Mínimo 30 operaciones por segmento para interpretar",
            "No implica autorización para activar estrategias",
        ],
        "claim": dx.get("claim")
        or {
            "declare_profitable": False,
            "activate_strategy": False,
            "reason": "Ejecuta el diagnóstico X para rellenar este panel.",
        },
    }

    return {
        **base,
        "etapa": "X",
        "when_to_trade": when,
        "diagnose_x": {
            "available": available,
            "per_variant": dx.get("per_variant"),
            "benchmarks": dx.get("benchmarks"),
            "bootstrap": dx.get("bootstrap"),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa X: diagnóstico por régimen. "
            "Si no hay segmentos robustos, el estado correcto es no operar / seguir investigando. "
            "A y B permanecen detenidos."
        ),
    }
