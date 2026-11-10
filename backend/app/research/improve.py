"""Informe «¿Cómo podemos mejorar mi bot?» — solo lectura + backtests aislados en memoria."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..active.economic_audit import audit_strategy_a
from .hypotheses_u import list_hypotheses


def audit_ai(execute: Callable) -> dict[str, Any]:
    row = execute(
        """SELECT
              COUNT(*) total,
              COUNT(*) FILTER (WHERE resolution_status='RESOLVED') resolved,
              COUNT(*) FILTER (WHERE resolution_status IS NULL OR resolution_status='PENDING') pending,
              COUNT(*) FILTER (WHERE calibrated_probability IS NOT NULL) with_calibration,
              COUNT(*) FILTER (WHERE observed_net_return > 0) positive_ret,
              COUNT(*) FILTER (WHERE observed_net_return <= 0) nonpos_ret,
              AVG(observed_net_return) FILTER (WHERE observed_net_return IS NOT NULL) avg_obs_ret
           FROM ml_predictions"""
    ).fetchone()
    model = execute(
        """SELECT id, version, status, validated_for_research, validated_for_paper_ai, created_at
           FROM ml_models ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    total = int((row or {}).get("total") or 0)
    resolved = int((row or {}).get("resolved") or 0)
    calib = int((row or {}).get("with_calibration") or 0)
    return {
        "predictions_total": total,
        "resolved": resolved,
        "pending": int((row or {}).get("pending") or 0),
        "with_calibration": calib,
        "positive_observed_returns": int((row or {}).get("positive_ret") or 0),
        "nonpositive_observed_returns": int((row or {}).get("nonpos_ret") or 0),
        "avg_observed_net_return": float(row["avg_obs_ret"]) if row and row.get("avg_obs_ret") is not None else None,
        "model": dict(model) if model else None,
        "execution_authorized": False,
        "paper_ai": False,
        "sufficient_for_live": False,
        "human": (
            "Hay predicciones de investigación evaluadas, pero sin probabilidad calibrada "
            "persistida. No hay evidencia suficiente para operar con IA."
            if calib == 0
            else "Hay calibración parcial; aún se requiere validación prospectiva antes de operar."
        ),
    }


def improve_report(
    execute: Callable,
    *,
    marks: dict[str, float] | None = None,
    backtest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    a = audit_strategy_a(execute, marks=marks or {})
    ai = audit_ai(execute)
    loss = a.get("loss_diagnosis") or {}
    closed = a.get("closed_performance") or {}
    capital = a.get("capital") or {}
    by_sym = a.get("by_symbol") or []
    by_exit = a.get("by_exit_reason") or []

    facts = [
        {
            "id": "trend_exits",
            "label": "Salidas por tendencia debilitada",
            "amount": loss.get("strategic_trend_exit_pnl"),
            "detail": "Hecho: la mayor parte del P/L negativo viene de muchas salidas pequeñas.",
        },
        {
            "id": "stops",
            "label": "Stop-loss (−1%)",
            "amount": loss.get("stop_loss_pnl"),
            "detail": "Hecho: pocos stops, pero con impacto grande por operación.",
        },
        {
            "id": "take_profits",
            "label": "Objetivos de ganancia (+2%)",
            "amount": loss.get("take_profit_pnl"),
            "detail": "Hecho: las pocas ganancias no compensan el resto.",
        },
        {
            "id": "fees",
            "label": "Comisiones acumuladas",
            "amount": -(loss.get("fees_total") or 0),
            "detail": "Hecho: coste de operar con frecuencia (no restar dos veces al P/L de fills).",
        },
        {
            "id": "slip",
            "label": "Deslizamiento registrado",
            "amount": -(loss.get("slip_total") or 0),
            "detail": "Hecho: ya incorporado en precios de fill del simulador.",
        },
    ]

    hypotheses_obs = [
        {
            "id": "h_noise_1m",
            "type": "hipótesis",
            "text": "El marco de 1 minuto genera salidas prematuras por ruido (trend_break frecuente).",
        },
        {
            "id": "h_cost_edge",
            "type": "hipótesis",
            "text": "El movimiento capturado medio no cubre fees+slip en la mayoría de rondas.",
        },
        {
            "id": "h_late_entry",
            "type": "hipótesis",
            "text": "Las entradas 4/5 pueden llegar tarde al impulso y salir en el retroceso.",
        },
    ]

    bt_summary = None
    if backtest:
        oos = backtest.get("out_of_sample") or {}
        rows = []
        for vid, r in oos.items():
            rows.append(
                {
                    "id": vid,
                    "name": next((h["title"] for h in list_hypotheses() if h["id"] == vid), vid),
                    "net_oos": r.get("net_vs_initial"),
                    "trades": r.get("buys"),
                    "win_rate": r.get("win_rate"),
                    "profit_factor": r.get("profit_factor"),
                    "expectancy": r.get("expectancy"),
                    "vs_cash": r.get("net_vs_initial"),
                }
            )
        bt_summary = {
            "bars": backtest.get("bars_per_symbol"),
            "walk_forward": backtest.get("walk_forward"),
            "oos_rows": sorted(rows, key=lambda x: (x.get("net_oos") is None, x.get("net_oos") or 0)),
            "claim": backtest.get("claim"),
        }

    dashboard = {
        "title": "¿Cómo podemos mejorar mi bot?",
        "why_lost": (
            f"El patrimonio virtual está en ≈{float(capital.get('equity') or 0):.2f} USDT "
            f"frente a 1.000 iniciales (Δ {float(capital.get('net_pnl') or 0):+.2f}). "
            "La frecuencia de operaciones no aportó valor neto: muchas salidas por tendencia "
            "debilitada y algunos stop-loss pesaron más que los pocos objetivos de ganancia."
        ),
        "main_causes": [
            {"motivo": f["label"], "impacto": f["amount"], "nota": f["detail"]}
            for f in facts
            if f.get("amount") is not None
        ],
        "by_crypto": [
            {
                "name": s["symbol"].replace("USDT", ""),
                "resultado": s.get("realized_pnl"),
                "cerradas": s.get("closed"),
                "ganadoras": s.get("wins"),
                "perdedoras": s.get("losses"),
            }
            for s in by_sym
        ],
        "costs": {
            "comisiones": loss.get("fees_total"),
            "deslizamiento": loss.get("slip_total"),
        },
        "experiments": [
            {
                "nombre": h["title"],
                "que_busca": h["human"],
                "estado": "En investigación (congelada)",
                "evidencia": "Insuficiente para activar",
            }
            for h in list_hypotheses()
        ],
        "comparison_note": (
            "Las variantes se comparan en backtest aislado (mismo costo y ventana). "
            "Ninguna se declara rentable solo por ganar en histórico."
        ),
        "insufficient": [
            "IA sin calibración → no operar",
            "Muestra OOS corta → no activar automáticamente",
            "A y B permanecen STOPPED por decisión de seguridad",
        ],
        "closed_stats": {
            "ganadoras": closed.get("wins"),
            "perdedoras": closed.get("losses"),
            "win_rate": closed.get("win_rate"),
            "profit_factor": closed.get("profit_factor"),
            "expectativa": closed.get("expectancy"),
        },
        "exit_breakdown": [
            {"motivo": x.get("label"), "n": x.get("n"), "resultado": x.get("realized_pnl")}
            for x in by_exit
        ],
    }

    return {
        "paper_only": True,
        "etapa": "U",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "a_status_note": "A debe permanecer STOPPED; este informe no la reactiva.",
        "b_status_note": "B permanece STOPPED; sin auto-inicio.",
        "capital": capital,
        "activity": a.get("activity"),
        "facts": facts,
        "hypotheses_observed": hypotheses_obs,
        "research_hypotheses": list_hypotheses(),
        "ai": ai,
        "backtest": bt_summary,
        "dashboard": dashboard,
        "integrity": a.get("integrity"),
        "risks": [
            "Sobreajuste a una ventana histórica corta.",
            "Cambiar solo el win rate sin mejorar expectativa neta.",
            "Aumentar exposición o quitar stops para 'arreglar' resultados.",
            "Activar IA sin calibración ni evidencia prospectiva.",
        ],
    }
