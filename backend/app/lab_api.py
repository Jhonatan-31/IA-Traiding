"""API for lab auto paper trading — isolated ledger; mutations require LAB_CONTROL_TOKEN."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .lab.auth import require_lab_token
from .lab.schema import ensure_lab_schema

router = APIRouter(prefix="/api/lab", tags=["lab"])


def _audit(execute, actor: str, action: str, detail: str) -> None:
    # Never write tokens/secrets into detail
    execute(
        "INSERT INTO lab_audit(actor, action, detail) VALUES(%s,%s,%s)",
        (actor, action, detail[:500]),
    )


@router.get("/status")
async def lab_status():
    from .lab.config import ACCOUNT_ID, STRATEGY
    from .lab.ledger import snapshot
    from .lab.valuation import fetch_marks, portfolio_valuation
    from .main import db, serial

    with db() as c:
        ensure_lab_schema(c.execute)
        state = c.execute("SELECT * FROM lab_executor_state WHERE id=1").fetchone()
        snap = snapshot(c.execute)
        fills = list(
            c.execute(
                """SELECT * FROM lab_orders WHERE account_id=%s AND status='FILLED'
                   ORDER BY id DESC LIMIT 30""",
                (ACCOUNT_ID,),
            )
        )
        rejected = list(
            c.execute(
                """SELECT * FROM lab_orders WHERE account_id=%s AND status='REJECTED'
                   ORDER BY id DESC LIMIT 40""",
                (ACCOUNT_ID,),
            )
        )
        pending = list(
            c.execute(
                """SELECT * FROM lab_orders
                   WHERE account_id=%s AND status IN ('NEW','VALIDATED')
                   ORDER BY id DESC LIMIT 30""",
                (ACCOUNT_ID,),
            )
        )
        trades = list(
            c.execute(
                """SELECT * FROM lab_trades WHERE account_id=%s ORDER BY id DESC LIMIT 50""",
                (ACCOUNT_ID,),
            )
        )
        sell_history = list(
            c.execute(
                """SELECT id, at, symbol, qty, price, fee, slip, reason, realized_pnl,
                          order_uid, candle_ms, strategy
                   FROM lab_trades
                   WHERE account_id=%s AND side='SELL'
                   ORDER BY id DESC LIMIT 40""",
                (ACCOUNT_ID,),
            )
        )
        cycles = list(
            c.execute(
                """SELECT * FROM lab_cycles ORDER BY id DESC LIMIT 20"""
            )
        )
        breaker_events = list(
            c.execute(
                """SELECT id, at, active, reason FROM lab_breaker_events
                   ORDER BY id DESC LIMIT 20"""
            )
        )
        buys = sum(1 for t in trades if t["side"] == "BUY")
        sells = sum(1 for t in trades if t["side"] == "SELL")
        fees = sum(float(t["fee"] or 0) for t in trades)
        slip_total = sum(float(t.get("slip") or 0) for t in trades)
        realized = sum(
            float(t["realized_pnl"]) for t in trades if t.get("realized_pnl") is not None
        )
        sma_cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        sma_pos = c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
        sma_tr = c.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
        virt = c.execute(
            "SELECT cash FROM virt_accounts WHERE id='research_sim'"
        ).fetchone()
        pos_syms = [p["symbol"] for p in snap["positions"]]
        cycles_1h = c.execute(
            """SELECT COUNT(*) AS n FROM lab_cycles
               WHERE started_at > NOW() - INTERVAL '1 hour'"""
        ).fetchone()["n"]
        eval_stats = c.execute(
            """SELECT
                 COUNT(*) AS evaluated,
                 COUNT(*) FILTER (WHERE decision='BUY') AS buy,
                 COUNT(*) FILTER (WHERE decision='SELL') AS sell,
                 COUNT(*) FILTER (WHERE decision='HOLD') AS hold,
                 COUNT(*) FILTER (WHERE cross_state IN ('golden','death')) AS crosses
               FROM lab_signal_evals
               WHERE at > NOW() - INTERVAL '24 hours'"""
        ).fetchone()
        recent_evals = list(
            c.execute(
                """SELECT at, symbol, candle_ms, sma10, sma50, cross_state, decision,
                          reason, data_status, risk_status
                   FROM lab_signal_evals ORDER BY id DESC LIMIT 40"""
            )
        )
        equity_hist = list(
            c.execute(
                """SELECT day, start_equity, end_equity FROM lab_equity_daily
                   WHERE account_id=%s ORDER BY day DESC LIMIT 30""",
                (ACCOUNT_ID,),
            )
        )
        monitor_alerts = list(
            c.execute(
                """SELECT id, at, code, severity, message, active, fingerprint
                   FROM lab_alerts WHERE active=TRUE ORDER BY id DESC LIMIT 30"""
            )
        )
        organic_signals = list(
            c.execute(
                """SELECT id, created_at, symbol, side, candle_ms, ref_price, meta_json
                   FROM lab_signals ORDER BY id DESC LIMIT 30"""
            )
        )
        accepted = c.execute(
            """SELECT COUNT(*) AS n FROM lab_orders
               WHERE account_id=%s AND status='FILLED'""",
            (ACCOUNT_ID,),
        ).fetchone()["n"]
        rejected_n = c.execute(
            """SELECT COUNT(*) AS n FROM lab_orders
               WHERE account_id=%s AND status='REJECTED'""",
            (ACCOUNT_ID,),
        ).fetchone()["n"]

    marks = await fetch_marks(pos_syms)
    with db() as c:
        ensure_lab_schema(c.execute)
        valuation = portfolio_valuation(c.execute, marks)

    alerts = []
    if valuation.get("valuation_status") == "INCOMPLETE":
        alerts.append(
            {
                "severity": "WARNING",
                "code": "stale_or_missing_marks",
                "message": "Valoración incompleta: faltan precios válidos.",
            }
        )
    if state and state.get("breaker_active"):
        alerts.append(
            {
                "severity": "ERROR",
                "code": "circuit_breaker",
                "message": f"Breaker activo: {state.get('breaker_reason')}",
            }
        )
    if state and state.get("last_error"):
        alerts.append(
            {
                "severity": "ERROR",
                "code": "last_executor_error",
                "message": str(state.get("last_error"))[:300],
            }
        )
    seen_codes = {a["code"] for a in alerts}
    for ma in monitor_alerts:
        if ma["code"] in seen_codes:
            continue
        alerts.append(
            {
                "severity": ma["severity"],
                "code": ma["code"],
                "message": ma["message"],
            }
        )
        seen_codes.add(ma["code"])

    last_cycle = cycles[0] if cycles else None
    meta = (state or {}).get("meta_json") or {}
    if isinstance(meta, str):
        import json as _json

        meta = _json.loads(meta)
    last_candle_ms = meta.get("last_candle_ms")
    no_opportunity = bool(
        last_cycle
        and int(last_cycle.get("signals_buy") or 0) == 0
        and int(last_cycle.get("signals_sell") or 0) == 0
        and int(last_cycle.get("symbols_scanned") or 0) > 0
        and last_cycle.get("ok")
    )

    return serial(
        {
            "mode": "PAPER_ONLY",
            "real_trading": False,
            "shadow_ai_executing": False,
            "authorized_strategy": STRATEGY,
            "executor": state,
            "ledger": snap,
            "valuation": valuation,
            "counts": {
                "buys": buys,
                "sells": sells,
                "pending_orders": len(pending),
                "rejected_orders": len(rejected),
                "filled_orders": len(fills),
            },
            "fees_simulated": fees,
            "slippage_estimated": slip_total,
            "realized_pnl": realized,
            "orders_pending": pending,
            "orders_rejected": rejected,
            "orders_filled_recent": fills,
            "trades": trades,
            "sell_history": sell_history,
            "positions": valuation.get("positions") or snap["positions"],
            "exit_policy": {
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
                "max_hold_bars": 48,
                "priority": [
                    "stale_or_missing_mark",
                    "stop_loss",
                    "take_profit",
                    "max_hold_bars",
                    "strategy_exit",
                ],
                "protective_sells_when_breaker": True,
                "sells_when_paused": False,
            },
            "cycles": cycles,
            "last_cycle": last_cycle,
            "breaker_events": breaker_events,
            "alerts": alerts,
            "observability": {
                "cycles_last_hour": int(cycles_1h),
                "signals_evaluated_24h": int(eval_stats["evaluated"] or 0) if eval_stats else 0,
                "crosses_detected_24h": int(eval_stats["crosses"] or 0) if eval_stats else 0,
                "decisions_24h": {
                    "buy": int(eval_stats["buy"] or 0) if eval_stats else 0,
                    "sell": int(eval_stats["sell"] or 0) if eval_stats else 0,
                    "hold": int(eval_stats["hold"] or 0) if eval_stats else 0,
                },
                "orders_accepted": int(accepted),
                "orders_rejected": int(rejected_n),
                "fees_accumulated": fees,
                "slippage_estimated": slip_total,
                "circuit_breaker_active": bool(state and state.get("breaker_active")),
                "last_candle_ms": last_candle_ms,
                "operating_without_opportunity": no_opportunity,
                "note_no_opportunity": (
                    "Sistema operativo: sin cruces SMA en el último ciclo (HOLD)."
                    if no_opportunity
                    else None
                ),
            },
            "equity_history": equity_hist,
            "signal_evals_recent": recent_evals,
            "organic_signals": organic_signals,
            "monitor_alerts": monitor_alerts,
            "integrity": {
                "sma_paper": {
                    "cash": float(sma_cash),
                    "positions": sma_pos,
                    "trades": sma_tr,
                },
                "research_sim_cash": float(virt["cash"]) if virt else None,
                "lab_cash": valuation.get("cash"),
                "lab_isolated": True,
            },
        }
    )


@router.post("/pause")
def lab_pause(
    reason: str = "dashboard_pause",
    _auth: str = Depends(require_lab_token),
):
    from .main import db, serial

    with db() as c:
        ensure_lab_schema(c.execute)
        c.execute(
            """UPDATE lab_executor_state SET
                 paused=TRUE, pause_reason=%s, status='PAUSED', updated_at=NOW()
               WHERE id=1""",
            (reason,),
        )
        _audit(c.execute, "api", "pause", reason)
    return serial({"paused": True, "reason": reason})


@router.post("/resume")
def lab_resume(
    reason: str = "dashboard_resume",
    _auth: str = Depends(require_lab_token),
):
    from .lab.risk import critical_condition_still_active
    from .main import db, serial

    with db() as c:
        ensure_lab_schema(c.execute)
        critical, crit_reason = critical_condition_still_active(c.execute)
        if critical:
            _audit(c.execute, "api", "resume_blocked", str(crit_reason))
            raise HTTPException(
                status_code=409,
                detail=f"resume_blocked_critical:{crit_reason}",
            )
        c.execute(
            """UPDATE lab_executor_state SET
                 paused=FALSE, pause_reason=NULL, status='OK', updated_at=NOW()
               WHERE id=1"""
        )
        _audit(c.execute, "api", "resume", reason)
    return serial(
        {
            "paused": False,
            "reason": reason,
            "note": "Pending orders not auto-fired on resume.",
        }
    )


@router.post("/cycle")
async def lab_cycle_once(_auth: str = Depends(require_lab_token)):
    from .lab.executor import run_lab_cycle
    from .main import db, serial

    return serial(await run_lab_cycle(db))
