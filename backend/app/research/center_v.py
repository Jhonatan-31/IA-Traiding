"""Payload del Centro de Investigación de Estrategias (Etapa V)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .forensic_a import forensic_rounds
from .improve import audit_ai
from .policies_v import list_policies


def research_center(
    execute: Callable,
    *,
    backtest_v: dict[str, Any] | None = None,
) -> dict[str, Any]:
    forensic = forensic_rounds(execute)
    ai = audit_ai(execute)
    policies = list_policies()
    oos = (backtest_v or {}).get("out_of_sample") or {}
    cards = []
    for p in policies:
        pid = p["id"]
        o = oos.get(pid) or oos.get(pid.replace("V_", "V_")) or {}
        # map ids
        key = pid if pid in oos else {"V_TREND": "V_TREND", "V_BREAK": "V_BREAK", "V_MEAN": "V_MEAN", "A_BASELINE": "A_BASELINE"}.get(pid)
        o = oos.get(key or "", {})
        status = p.get("status") or "research"
        if pid in {"A_BASELINE", "B_BASELINE"}:
            ui_status = "Baseline (inmutable)"
        elif pid == "V_IA":
            ui_status = "Solo observación"
        elif o and (o.get("net_vs_initial") or 0) > 0 and (o.get("closed_rounds") or 0) >= 5:
            ui_status = "Candidata para prueba virtual"  # still needs explicit auth
        elif o and (o.get("buys") == 0):
            ui_status = "Rechazada (sin operaciones OOS)"
        elif o:
            ui_status = "Rechazada (OOS no positivo)"
        else:
            ui_status = "En investigación"

        cards.append(
            {
                "id": pid,
                "name": p.get("title"),
                "how_it_works": p.get("human"),
                "markets": ["BTC", "ETH", "SOL"],
                "evaluation_period": (backtest_v or {}).get("data_span_note")
                or "Ventana corta 1m (API pública); ampliar a 12–24m pendiente.",
                "net_oos": o.get("net_vs_initial"),
                "drawdown_oos": o.get("max_drawdown_proxy"),
                "costs_oos": {
                    "fees": o.get("fees"),
                    "slip": o.get("slips"),
                },
                "vs_cash_oos": o.get("net_vs_initial"),
                "evidence": "Backtest walk-forward aislado" if o else "Pendiente de backtest",
                "limitations": [
                    "Muestra histórica corta en este corte",
                    "Sin garantía de rentabilidad",
                    "No activa carteras operativas",
                ],
                "status_label": ui_status,
                "frozen": p.get("frozen", True),
                "execution_authorized": p.get("execution_authorized", False),
            }
        )

    vt = forensic["verified_totals"]
    return {
        "paper_only": True,
        "etapa": "V",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safety": {
            "a_must_remain_stopped": True,
            "b_must_remain_stopped": True,
            "paper_ai": False,
        },
        "forensic_summary": {
            "cash": vt.get("db_cash"),
            "reconstructed_cash": vt.get("reconstructed_cash"),
            "discrepancy": vt.get("cash_discrepancy"),
            "closed_rounds": vt.get("closed_rounds"),
            "realized_pnl": vt.get("realized_pnl_sum"),
            "fees": vt.get("fees_sum"),
            "slip": vt.get("slip_sum"),
            "matches_prior_report": vt.get("matches_etapa_u_report"),
            "loss_by_exit": forensic["loss_sources"]["by_exit_reason_pnl"],
        },
        "ai": ai,
        "strategy_cards": cards,
        "backtest": {
            "available": bool(backtest_v),
            "walk_forward": (backtest_v or {}).get("walk_forward"),
            "claim": (backtest_v or {}).get("claim"),
            "approval_gate": (backtest_v or {}).get("approval_gate"),
            "data_span_note": (backtest_v or {}).get("data_span_note"),
        },
        "external_research_doc": "docs/etapa_v_investigacion_externa.md",
        "conclusion": (
            "Ninguna estrategia nueva se activa. Si OOS no es positivo y robusto, "
            "el estado correcto es rechazar o seguir investigando — no fabricar rentabilidad."
        ),
    }
