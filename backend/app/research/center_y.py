"""Panel Etapa Y — ¿Estamos vendiendo demasiado pronto?"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .center_x import research_center_x


def research_center_y(
    execute: Callable,
    *,
    backtest_v=None,
    backtest_w=None,
    diagnose_x=None,
    exits_y=None,
) -> dict[str, Any]:
    base = research_center_x(
        execute, backtest_v=backtest_v, backtest_w=backtest_w, diagnose_x=diagnose_x
    )
    ey = exits_y or {}
    available = bool(ey.get("available"))
    rows = []
    for entry_mode, ys in (ey.get("results") or {}).items():
        for yid, pack in (ys or {}).items():
            o = pack.get("out_of_sample") or {}
            rows.append(
                {
                    "entry": entry_mode,
                    "exit": yid,
                    "title": (pack.get("policy") or {}).get("title"),
                    "n": o.get("n"),
                    "net_usdt": o.get("net_vs_initial"),
                    "expectancy": o.get("expectancy"),
                    "avg_mfe": o.get("avg_mfe"),
                    "avg_capture_ratio": o.get("avg_capture_ratio"),
                    "pct_gave_back": o.get("pct_gave_back_to_loss"),
                    "drawdown": o.get("max_drawdown_proxy"),
                    "fees": o.get("fees"),
                }
            )

    selling_soon = {
        "title": "¿Estamos vendiendo demasiado pronto?",
        "available": available,
        "disclaimer": (
            "El máximo favorable observado (MFE) no es una ganancia que se podía capturar con certeza."
        ),
        "diagnosis_y0": ey.get("diagnosis_y0") or {},
        "comparison_rows": rows,
        "candidates": ey.get("candidates") or [],
        "claim": ey.get("claim")
        or {"activate": False, "reason": "Ejecuta el análisis de salidas Y."},
        "limitations": [
            "Holdout W consumido; sin Parquet post-oct-2025 para OOS temporal nuevo",
            "Orden intrabar más fino que 1m desconocido (política SL-first)",
            "Entradas fijas — no se buscan nuevas señales en esta etapa",
            "Sin activación automática",
        ],
        "units": ey.get("units") or {},
    }
    return {
        **base,
        "etapa": "Y",
        "selling_too_soon": selling_soon,
        "exits_y": {"available": available, "claim": ey.get("claim")},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "conclusion": (
            "Etapa Y: investigación de salidas. "
            "Si Y1–Y4 no mejoran Y0 de forma robusta, se descarta perseguir micro-ajustes "
            "sobre las mismas entradas. A y B detenidos."
        ),
    }
