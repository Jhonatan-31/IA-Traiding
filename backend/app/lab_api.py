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

    last_cycle = cycles[0] if cycles else None
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
            "realized_pnl": realized,
            "orders_pending": pending,
            "orders_rejected": rejected,
            "orders_filled_recent": fills,
            "trades": trades,
            "positions": valuation.get("positions") or snap["positions"],
            "cycles": cycles,
            "last_cycle": last_cycle,
            "breaker_events": breaker_events,
            "alerts": alerts,
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
