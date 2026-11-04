"""Etapa Q — compare paper ledgers / shadow research using only persisted facts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _resolved_prediction_rows(execute: Callable) -> list[dict[str, Any]]:
    """Only RESOLVED SHADOW_LIVE with persisted outcomes — never invents prices."""
    try:
        from .prospect.report import decision_result_rows
    except Exception:
        return []
    rows = decision_result_rows(execute, experiment_type="SHADOW_LIVE", limit=500)
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("resolution_status") != "RESOLVED":
            continue
        out.append(
            {
                "symbol": r.get("symbol"),
                "action": r.get("action"),
                "probability": r.get("probability"),
                "probability_note": r.get("probability_note"),
                "entry_price_observed": r.get("entry_price_observed"),
                "exit_price_observed": r.get("exit_price_observed"),
                "asset_return": r.get("asset_return"),
                "hypothetical_net_if_buy": r.get("hypothetical_net_if_buy"),
                "classification_hit": r.get("classification_hit"),
                "data_quality": r.get("data_quality"),
                "signal_ts": r.get("signal_ts"),
                "resolved_at": r.get("resolved_at"),
                "result_class": r.get("result_class"),
                "executed_trade": False,
                "hold_counted_as_trade": False,
                "experiment_type": r.get("experiment_type"),
            }
        )
    return out


def _gap_rows(execute: Callable, table: str, *, threshold_sec: int = 450) -> list[dict]:
    """Detect omitted cycles from persisted timestamps (host sleep / downtime)."""
    rows = list(
        execute(
            f"""SELECT id, started_at, finished_at,
                      EXTRACT(EPOCH FROM (started_at - LAG(finished_at) OVER (ORDER BY id)))::int AS gap_sec
               FROM {table}
               ORDER BY id"""
        )
    )
    out = []
    for r in rows:
        gap = r.get("gap_sec")
        if gap is None or int(gap) < threshold_sec:
            continue
        out.append(
            {
                "table": table,
                "after_cycle_id": int(r["id"]) - 1 if r["id"] else None,
                "next_cycle_id": int(r["id"]),
                "gap_sec": int(gap),
                "approx_cycles_omitted": max(0, int(round(int(gap) / 300.0)) - 1),
                "resumed_at": r["started_at"].isoformat()
                if hasattr(r["started_at"], "isoformat")
                else str(r["started_at"]),
                "note": "No se reconstruyen operaciones durante el hueco.",
            }
        )
    return out


def build_performance_compare(
    execute: Callable,
    *,
    lab_valuation: dict[str, Any] | None = None,
    sma_risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Read-only comparison. Never invents PnL for unresolved Shadow decisions.
    Ledgers stay separate: SMA paper / lab_auto / research_sim.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    sma_cash = execute("SELECT cash FROM account WHERE id=1").fetchone()
    sma_pos = list(execute("SELECT symbol, qty, cost FROM positions ORDER BY symbol"))
    sma_trades_n = execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
    sma_buys = execute("SELECT COUNT(*) AS n FROM trades WHERE side='BUY'").fetchone()["n"]
    sma_sells = execute("SELECT COUNT(*) AS n FROM trades WHERE side='SELL'").fetchone()["n"]

    lab_acc = execute(
        "SELECT id, cash, initial_capital FROM lab_accounts WHERE id='lab_auto'"
    ).fetchone()
    lab_pos = list(
        execute(
            "SELECT symbol, qty, cost, entry_price FROM lab_positions WHERE account_id='lab_auto' ORDER BY symbol"
        )
    )
    lab_trades = list(
        execute(
            """SELECT side, COUNT(*) AS n, COALESCE(SUM(fee),0) AS fees,
                      COALESCE(SUM(realized_pnl),0) AS rpnl,
                      COALESCE(SUM(slip),0) AS slip
               FROM lab_trades WHERE account_id='lab_auto' GROUP BY side"""
        )
    )
    lab_orders = list(
        execute(
            """SELECT status, COUNT(*) AS n FROM lab_orders
               WHERE account_id='lab_auto' GROUP BY status"""
        )
    )
    lab_trade_rows = list(
        execute(
            """SELECT id, at, symbol, side, qty, price, fee, slip, realized_pnl, reason
               FROM lab_trades WHERE account_id='lab_auto' ORDER BY id"""
        )
    )
    lab_by_symbol = list(
        execute(
            """SELECT symbol,
                      COUNT(*) FILTER (WHERE side='BUY') AS buys,
                      COUNT(*) FILTER (WHERE side='SELL') AS sells,
                      COALESCE(SUM(fee),0) AS fees,
                      COALESCE(SUM(slip),0) AS slip,
                      COALESCE(SUM(realized_pnl),0) AS realized_pnl
               FROM lab_trades WHERE account_id='lab_auto'
               GROUP BY symbol ORDER BY symbol"""
        )
    )

    research = execute(
        "SELECT id, cash, initial_capital FROM virt_accounts WHERE id='research_sim'"
    ).fetchone()
    if not research:
        research = execute(
            "SELECT id, cash, initial_capital FROM lab_accounts WHERE id='research_sim'"
        ).fetchone()
    if not research:
        research = {"id": "research_sim", "cash": None, "initial_capital": None}

    shadow_counts = list(
        execute(
            """SELECT d.resolution_status, d.action, COUNT(*) AS n
               FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE'
               GROUP BY 1, 2 ORDER BY 1, 2"""
        )
    )
    shadow_pending = execute(
        """SELECT COUNT(*) AS n FROM prospect_decisions d
           JOIN prospect_experiments e ON e.id=d.experiment_id
           WHERE e.experiment_type='SHADOW_LIVE' AND d.resolution_status='PENDING'"""
    ).fetchone()["n"]
    shadow_resolved = execute(
        """SELECT COUNT(*) AS n FROM prospect_decisions d
           JOIN prospect_experiments e ON e.id=d.experiment_id
           WHERE e.experiment_type='SHADOW_LIVE' AND d.resolution_status='RESOLVED'"""
    ).fetchone()["n"]

    earliest_ready = execute(
        """SELECT MIN(d.candle_open_ms + (d.horizon_bars + 1) * 3600000) AS ready_ms
           FROM prospect_decisions d
           JOIN prospect_experiments e ON e.id=d.experiment_id
           WHERE e.experiment_type='SHADOW_LIVE' AND d.resolution_status='PENDING'"""
    ).fetchone()
    ready_now_n = execute(
        """SELECT COUNT(*) AS n FROM prospect_decisions d
           JOIN prospect_experiments e ON e.id=d.experiment_id
           WHERE e.experiment_type='SHADOW_LIVE'
             AND d.resolution_status='PENDING'
             AND (d.candle_open_ms + (d.horizon_bars + 1) * 3600000) <= %s""",
        (now_ms,),
    ).fetchone()["n"]

    ready_ms = earliest_ready["ready_ms"] if earliest_ready else None
    ready_utc = (
        datetime.fromtimestamp(int(ready_ms) / 1000.0, tz=timezone.utc).isoformat()
        if ready_ms is not None
        else None
    )

    lab_eq_daily = list(
        execute(
            """SELECT day, start_equity, end_equity FROM lab_equity_daily
               WHERE account_id='lab_auto' ORDER BY day"""
        )
    )
    sma_scans = list(
        execute(
            """SELECT id, at, equity FROM scans
               WHERE equity IS NOT NULL ORDER BY id"""
        )
    )

    downtime = _gap_rows(execute, "shadow_scheduler_cycles") + _gap_rows(
        execute, "lab_cycles"
    )

    lab_by_side = {r["side"]: dict(r) for r in lab_trades}
    order_by_status = {r["status"]: int(r["n"]) for r in lab_orders}

    sma_invested = sum(float(p["cost"]) for p in sma_pos)
    lab_invested = sum(float(p["cost"]) for p in lab_pos)

    lab_fees = sum(float(v.get("fees") or 0) for v in lab_by_side.values())
    lab_slip = sum(float(v.get("slip") or 0) for v in lab_by_side.values())
    lab_rpnl = sum(float(v.get("rpnl") or 0) for v in lab_by_side.values())
    lab_equity = (lab_valuation or {}).get("equity_estimate")
    lab_init = _f(lab_acc["initial_capital"]) if lab_acc else None
    lab_net_return = None
    if lab_equity is not None and lab_init:
        lab_net_return = (float(lab_equity) - float(lab_init)) / float(lab_init)

    closed_natural = [
        {
            "id": int(t["id"]),
            "at": t["at"].isoformat() if hasattr(t["at"], "isoformat") else str(t["at"]),
            "symbol": t["symbol"],
            "side": t["side"],
            "qty": _f(t["qty"]),
            "price": _f(t["price"]),
            "fee": _f(t["fee"]),
            "slip": _f(t["slip"]),
            "realized_pnl": _f(t["realized_pnl"]),
            "reason": t["reason"],
            "is_verification_or_demo": bool(
                t["reason"]
                and (
                    "demo" in str(t["reason"]).lower()
                    or "verif" in str(t["reason"]).lower()
                )
            ),
        }
        for t in lab_trade_rows
        if t["side"] == "SELL"
    ]

    return {
        "generated_at": now_iso,
        "mode": "PAPER_ONLY",
        "note": "Comparación factual. Shadow PENDING no aporta PnL ejecutado.",
        "ledgers": {
            "sma_paper": {
                "initial_capital": (sma_risk or {}).get("initial_capital"),
                "cash": _f(sma_cash["cash"]) if sma_cash else None,
                "invested_cost": sma_invested,
                "open_positions": len(sma_pos),
                "trades_total": int(sma_trades_n),
                "buys": int(sma_buys),
                "sells": int(sma_sells),
                "equity_estimate": (sma_risk or {}).get("equity_estimate"),
                "unrealized_pnl": (sma_risk or {}).get("unrealized_pnl"),
                "realized_pnl": (sma_risk or {}).get("realized_pnl"),
                "fees_estimated": (sma_risk or {}).get("fees_estimated"),
                "drawdown": (sma_risk or {}).get("drawdown"),
                "net_return_vs_initial": (
                    (
                        float((sma_risk or {}).get("equity_estimate"))
                        - float((sma_risk or {}).get("initial_capital"))
                    )
                    / float((sma_risk or {}).get("initial_capital"))
                    if (sma_risk or {}).get("equity_estimate") is not None
                    and (sma_risk or {}).get("initial_capital")
                    else None
                ),
                "positions": [
                    {
                        "symbol": p["symbol"],
                        "qty": _f(p["qty"]),
                        "cost": _f(p["cost"]),
                    }
                    for p in sma_pos
                ],
            },
            "lab_auto": {
                "cash": _f(lab_acc["cash"]) if lab_acc else None,
                "initial_capital": lab_init,
                "invested_cost": lab_invested,
                "open_positions": len(lab_pos),
                "orders_by_status": order_by_status,
                "trades_by_side": {
                    k: {
                        "n": int(v["n"]),
                        "fees": _f(v["fees"]),
                        "slip": _f(v.get("slip")),
                        "realized_pnl": _f(v["rpnl"]),
                    }
                    for k, v in lab_by_side.items()
                },
                "by_symbol": [
                    {
                        "symbol": r["symbol"],
                        "buys": int(r["buys"]),
                        "sells": int(r["sells"]),
                        "fees": _f(r["fees"]),
                        "slip": _f(r["slip"]),
                        "realized_pnl": _f(r["realized_pnl"]),
                    }
                    for r in lab_by_symbol
                ],
                "closed_sells": closed_natural,
                "fees_total": lab_fees,
                "slip_total": lab_slip,
                "realized_pnl_ledger": lab_rpnl,
                "net_return_vs_initial": lab_net_return,
                "valuation_status": (lab_valuation or {}).get("valuation_status"),
                "equity_estimate": lab_equity,
                "unrealized_pnl": (lab_valuation or {}).get("unrealized_pnl"),
                "realized_pnl": (lab_valuation or {}).get("realized_pnl"),
                "fees_accumulated": (lab_valuation or {}).get("fees_accumulated"),
                "drawdown_vs_peak": (lab_valuation or {}).get("drawdown_vs_peak"),
                "positions": [
                    {
                        "symbol": p["symbol"],
                        "qty": _f(p["qty"]),
                        "cost": _f(p["cost"]),
                        "entry_price": _f(p.get("entry_price")),
                    }
                    for p in lab_pos
                ],
            },
            "research_sim": {
                "cash": _f(research.get("cash")) if research else None,
                "initial_capital": _f(research.get("initial_capital")) if research else None,
                "note": "Ledger virtual Shadow — no ejecuta fills reales ni paper SMA.",
                "net_return_vs_initial": 0.0
                if research and _f(research.get("cash")) == _f(research.get("initial_capital"))
                else None,
            },
        },
        "equity_curves": {
            "sma_scans": [
                {
                    "t": s["at"].isoformat()
                    if hasattr(s["at"], "isoformat")
                    else str(s["at"]),
                    "equity": _f(s["equity"]),
                    "scan_id": int(s["id"]),
                }
                for s in sma_scans
            ],
            "lab_daily": [
                {
                    "day": str(r["day"]),
                    "start_equity": _f(r["start_equity"]),
                    "end_equity": _f(r["end_equity"]),
                }
                for r in lab_eq_daily
            ],
            "note": "Series observadas (scans / lab_equity_daily). Sin interpolación del hueco de suspensión.",
        },
        "operational_coverage": {
            "downtime_gaps": downtime,
            "host_sleep_confirmed_utc": {
                "sleep": "2026-11-03T22:51:26Z",
                "wake": "2026-11-03T23:31:14Z",
                "source": "Windows Event Viewer Kernel-Power / Power-Troubleshooter",
            },
            "policy": "No se reconstruyen trades omitidos durante suspensión del host.",
        },
        "shadow_live": {
            "pending": int(shadow_pending),
            "resolved": int(shadow_resolved),
            "invalid": int(
                execute(
                    """SELECT COUNT(*) AS n FROM prospect_decisions d
                       JOIN prospect_experiments e ON e.id=d.experiment_id
                       WHERE e.experiment_type='SHADOW_LIVE' AND d.resolution_status='INVALID'"""
                ).fetchone()["n"]
            ),
            "outcomes_persisted": int(
                execute("SELECT COUNT(*) AS n FROM prospect_outcomes").fetchone()["n"]
            ),
            "ready_now": int(ready_now_n),
            "sample_sufficient": int(shadow_resolved) >= 30,
            "pending_reason_summary": (
                {
                    "primary": "horizon_not_complete_or_clock_before_ready_after_close",
                    "detail": "Resolver exige vela de salida 1h cerrada (open=entry+6h); ready_after = cierre de esa vela.",
                    "first_batch_ready_after_utc": ready_utc,
                    "seconds_until_first_ready": (
                        max(0, int((int(ready_ms) - now_ms) / 1000))
                        if ready_ms is not None
                        else None
                    ),
                }
                if int(shadow_resolved) == 0
                else None
            ),
            "resolved_predictions": _resolved_prediction_rows(execute),
            "by_status_action": [
                {
                    "resolution_status": r["resolution_status"],
                    "action": r["action"],
                    "n": int(r["n"]),
                }
                for r in shadow_counts
            ],
            "earliest_horizon_ready_after_utc": ready_utc,
            "pnl_available": int(shadow_resolved) > 0,
            "evaluation_vs_portfolio": {
                "predictive_eval": "prospect_outcomes /api/prospect/report (hipotético)",
                "executable_portfolio": "lab_auto / sma_paper ledgers only",
                "note": "HOLD no es trade; BUY Shadow no muta carteras ejecutables.",
            },
            "pnl_note": (
                "Sin métricas de retorno Shadow LIVE hasta RESOLVED. No forzar resoluciones."
                if int(shadow_resolved) == 0
                else "Usar /api/prospect/report para métricas resueltas."
            ),
            "strategy_claim_allowed": False,
            "strategy_claim_note": "No declarar rentabilidad de estrategia con muestra pequeña o n=0 resueltas.",
        },
        "integrity": {
            "ledgers_separated": True,
            "paper_only": True,
            "shadow_executing": False,
            "paper_ai_disabled": True,
        },
    }
