"""API for lab auto paper trading — isolated ledger."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .lab.schema import ensure_lab_schema

router = APIRouter(prefix="/api/lab", tags=["lab"])


def _audit(execute, actor: str, action: str, detail: str) -> None:
    execute(
        "INSERT INTO lab_audit(actor, action, detail) VALUES(%s,%s,%s)",
        (actor, action, detail),
    )


@router.get("/status")
def lab_status():
    from .lab.config import ACCOUNT_ID, STRATEGY
    from .lab.ledger import snapshot
    from .lab.risk import lab_equity
    from .main import db, serial

    with db() as c:
        ensure_lab_schema(c.execute)
        state = c.execute("SELECT * FROM lab_executor_state WHERE id=1").fetchone()
        snap = snapshot(c.execute)
        eq = lab_equity(c.execute)
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
                   ORDER BY id DESC LIMIT 30""",
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
        buys = sum(1 for t in trades if t["side"] == "BUY")
        sells = sum(1 for t in trades if t["side"] == "SELL")
        fees = sum(float(t["fee"] or 0) for t in trades)
        realized = sum(
            float(t["realized_pnl"]) for t in trades if t.get("realized_pnl") is not None
        )
        # SMA paper untouched check
        sma_cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
        sma_pos = c.execute("SELECT COUNT(*) AS n FROM positions").fetchone()["n"]
        sma_tr = c.execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"]
        virt = c.execute(
            "SELECT cash FROM virt_accounts WHERE id='research_sim'"
        ).fetchone()
    return serial(
        {
            "mode": "PAPER_ONLY",
            "real_trading": False,
            "shadow_ai_executing": False,
            "authorized_strategy": STRATEGY,
            "executor": state,
            "ledger": snap,
            "equity": {
                "cash": float(eq["cash"]),
                "invested_cost": float(eq["invested_cost"]),
                "equity_mark_or_cost": float(eq["equity"]),
                "positions_n": eq["positions_n"],
            },
            "counts": {
                "buys": buys,
                "sells": sells,
                "pending_orders": len(pending),
                "rejected_orders": len(rejected),
                "filled_orders": len(fills),
            },
            "fees_simulated": fees,
            "realized_pnl": realized,
            "unrealized_pnl_note": "Mark-to-market when live marks available; else cost basis.",
            "orders_pending": pending,
            "orders_rejected": rejected,
            "orders_filled_recent": fills,
            "trades": trades,
            "positions": snap["positions"],
            "integrity": {
                "sma_paper": {"cash": float(sma_cash), "positions": sma_pos, "trades": sma_tr},
                "research_sim_cash": float(virt["cash"]) if virt else None,
                "lab_isolated": True,
            },
        }
    )


@router.post("/pause")
def lab_pause(
    reason: str = "dashboard_pause",
    x_lab_token: str | None = Header(default=None, alias="X-Lab-Token"),
):
    """Pause lab executor. Requires X-Lab-Token matching LAB_CONTROL_TOKEN env (or 'paper')."""
    import os

    from .main import db, serial

    expected = os.environ.get("LAB_CONTROL_TOKEN", "paper")
    if (x_lab_token or "") != expected:
        raise HTTPException(401, "unauthorized lab control")
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
    x_lab_token: str | None = Header(default=None, alias="X-Lab-Token"),
):
    import os

    from .main import db, serial

    expected = os.environ.get("LAB_CONTROL_TOKEN", "paper")
    if (x_lab_token or "") != expected:
        raise HTTPException(401, "unauthorized lab control")
    with db() as c:
        ensure_lab_schema(c.execute)
        # Do not auto-revive NEW orders unexpectedly — leave queue as-is
        c.execute(
            """UPDATE lab_executor_state SET
                 paused=FALSE, pause_reason=NULL, status='OK', updated_at=NOW()
               WHERE id=1"""
        )
        _audit(c.execute, "api", "resume", reason)
    return serial({"paused": False, "reason": reason, "note": "Pending orders not auto-fired on resume."})


@router.post("/cycle")
async def lab_cycle_once(
    x_lab_token: str | None = Header(default=None, alias="X-Lab-Token"),
):
    import os

    from .lab.executor import run_lab_cycle
    from .main import db, serial

    expected = os.environ.get("LAB_CONTROL_TOKEN", "paper")
    if (x_lab_token or "") != expected:
        raise HTTPException(401, "unauthorized lab control")
    return serial(await run_lab_cycle(db))
