"""Etapa T APIs — Strategy B control + multi-strategy comparison cards."""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Query

from ..lab.auth import require_lab_token
from ..ohlcv import fetch_klines
from . import ACCOUNT_B, B_EXECUTION_AUTHORIZED, INITIAL_CASH, POLICY_B_VERSION
from .control import start_bot, stop_bot
from .policy_b import POLICY_DOC, human_reason
from .policy_c import validation_report
from .schema import ensure_active_schema

router = APIRouter(prefix="/api/active", tags=["active"])


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@router.get("/strategies")
async def strategies_overview():
    """Three strategy cards: A (demo), B (active), C (AI observe)."""
    from ..main import db, serial
    from ..demo import ACCOUNT_ID as DEMO_ID
    from ..demo.schema import ensure_demo_schema

    out: dict[str, Any] = {"paper_only": True, "strategies": []}

    with db() as c:
        ensure_demo_schema(c.execute)
        ensure_active_schema(c.execute)

        # --- A: Demo baseline ---
        d_acc = c.execute("SELECT * FROM demo_accounts WHERE id=%s", (DEMO_ID,)).fetchone()
        d_st = c.execute("SELECT * FROM demo_state WHERE id=1").fetchone()
        d_pos = list(
            c.execute("SELECT * FROM demo_positions WHERE account_id=%s", (DEMO_ID,))
        )
        d_tc = c.execute(
            """SELECT COUNT(*) FILTER (WHERE side='BUY') buys,
                      COUNT(*) FILTER (WHERE side='SELL') sells,
                      COALESCE(SUM(realized_pnl),0) rpnl,
                      COALESCE(SUM(fee),0) fees
               FROM demo_trades WHERE account_id=%s""",
            (DEMO_ID,),
        ).fetchone()
        d_last = c.execute(
            """SELECT action, reason, at, symbol FROM demo_decisions
               WHERE account_id=%s ORDER BY id DESC LIMIT 1""",
            (DEMO_ID,),
        ).fetchone()

        # --- B: Active ---
        b_acc = c.execute("SELECT * FROM active_accounts WHERE id=%s", (ACCOUNT_B,)).fetchone()
        b_st = c.execute("SELECT * FROM active_state WHERE id=1").fetchone()
        b_pos = list(
            c.execute("SELECT * FROM active_positions WHERE account_id=%s", (ACCOUNT_B,))
        )
        b_tc = c.execute(
            """SELECT COUNT(*) FILTER (WHERE side='BUY') buys,
                      COUNT(*) FILTER (WHERE side='SELL') sells,
                      COALESCE(SUM(realized_pnl),0) rpnl,
                      COALESCE(SUM(fee),0) fees
               FROM active_trades WHERE account_id=%s""",
            (ACCOUNT_B,),
        ).fetchone()
        b_last = c.execute(
            """SELECT action, reason, human_reason, at, symbol FROM active_decisions
               WHERE account_id=%s ORDER BY id DESC LIMIT 1""",
            (ACCOUNT_B,),
        ).fetchone()

        c_rep = validation_report(c.execute)

    # marks for equity (best-effort)
    async def _marks(positions: list) -> dict[str, float]:
        marks: dict[str, float] = {}
        if not positions:
            return marks
        try:
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "ResearchPaperBot/active"}) as client:
                for p in positions:
                    try:
                        k = await fetch_klines(client, p["symbol"], "1m", limit=3, use_cache=True)
                        closed = [x for x in k["candles"] if x.get("is_closed", True)]
                        if closed:
                            marks[p["symbol"]] = float(closed[-1]["close"])
                    except Exception:
                        continue
        except Exception:
            pass
        return marks

    d_marks = await _marks(d_pos)
    b_marks = await _marks(b_pos)

    def equity(acc, positions, marks):
        if not acc:
            return None
        cash = float(acc["cash"])
        mv = 0.0
        for p in positions:
            px = marks.get(p["symbol"])
            if px is None:
                px = float(p["entry_price"])
            mv += float(p["qty"]) * px
        return cash + mv

    d_eq = equity(d_acc, d_pos, d_marks)
    b_eq = equity(b_acc, b_pos, b_marks)

    out["strategies"] = [
        {
            "id": "A",
            "name": "Conservadora",
            "ledger": DEMO_ID,
            "policy_version": "demo_policy_v1_20261103",
            "execution_authorized": True,
            "status": (d_st or {}).get("status") or "STOPPED",
            "cash": _f((d_acc or {}).get("cash")),
            "equity": d_eq,
            "buys": int((d_tc or {}).get("buys") or 0),
            "sells": int((d_tc or {}).get("sells") or 0),
            "open_positions": len(d_pos),
            "realized_pnl": _f((d_tc or {}).get("rpnl")),
            "fees": _f((d_tc or {}).get("fees")),
            "risk_level": "Bajo–moderado",
            "last_decision": serial(d_last) if d_last else None,
            "last_reason_human": human_reason(str((d_last or {}).get("reason") or ""))
            if d_last
            else None,
            "controls": {"start_stop": True, "path": "/api/demo"},
        },
        {
            "id": "B",
            "name": "Trading Activo",
            "ledger": ACCOUNT_B,
            "policy_version": POLICY_B_VERSION,
            "execution_authorized": B_EXECUTION_AUTHORIZED,
            "status": (b_st or {}).get("status") or "STOPPED",
            "cash": _f((b_acc or {}).get("cash")),
            "equity": b_eq,
            "initial_capital": INITIAL_CASH,
            "buys": int((b_tc or {}).get("buys") or 0),
            "sells": int((b_tc or {}).get("sells") or 0),
            "open_positions": len(b_pos),
            "realized_pnl": _f((b_tc or {}).get("rpnl")),
            "fees": _f((b_tc or {}).get("fees")),
            "risk_level": "Moderado (más señales estructurales)",
            "last_decision": serial(b_last) if b_last else None,
            "last_reason_human": (b_last or {}).get("human_reason")
            or (human_reason(str((b_last or {}).get("reason") or "")) if b_last else None),
            "controls": {"start_stop": True, "path": "/api/active"},
            "policy_doc": POLICY_DOC,
        },
        {
            "id": "C",
            "name": "IA Experimental",
            "ledger": "observation",
            "policy_version": c_rep["policy_version"],
            "execution_authorized": False,
            "status": c_rep["status"],
            "cash": None,
            "equity": None,
            "buys": 0,
            "sells": 0,
            "open_positions": 0,
            "realized_pnl": None,
            "risk_level": "Solo investigación",
            "last_decision": None,
            "last_reason_human": c_rep["message"],
            "controls": {"start_stop": False},
            "validation": c_rep,
        },
    ]
    return out


@router.get("/b/status")
async def active_b_status():
    from ..main import db, serial

    with db() as c:
        ensure_active_schema(c.execute)
        acc = c.execute("SELECT * FROM active_accounts WHERE id=%s", (ACCOUNT_B,)).fetchone()
        st = c.execute("SELECT * FROM active_state WHERE id=1").fetchone()
        positions = list(
            c.execute(
                "SELECT * FROM active_positions WHERE account_id=%s ORDER BY symbol",
                (ACCOUNT_B,),
            )
        )
        tc = c.execute(
            """SELECT COUNT(*) FILTER (WHERE side='BUY') buys,
                      COUNT(*) FILTER (WHERE side='SELL') sells,
                      COALESCE(SUM(fee),0) fees,
                      COALESCE(SUM(slip),0) slip,
                      COALESCE(SUM(realized_pnl),0) rpnl
               FROM active_trades WHERE account_id=%s""",
            (ACCOUNT_B,),
        ).fetchone()
        dec = c.execute(
            """SELECT COUNT(*) FILTER (WHERE action='BUY') buy_n,
                      COUNT(*) FILTER (WHERE action='SELL') sell_n,
                      COUNT(*) FILTER (WHERE action='HOLD') hold_n,
                      COUNT(*) FILTER (WHERE executed) executed_n
               FROM active_decisions WHERE account_id=%s""",
            (ACCOUNT_B,),
        ).fetchone()
    return {
        "account_id": ACCOUNT_B,
        "policy_version": POLICY_B_VERSION,
        "execution_authorized": B_EXECUTION_AUTHORIZED,
        "bot_status": (st or {}).get("status"),
        "cash": _f((acc or {}).get("cash")),
        "peak_equity": _f((acc or {}).get("peak_equity")),
        "initial_capital": _f((acc or {}).get("initial_capital")),
        "positions": [serial(p) for p in positions],
        "trade_counts": serial(tc),
        "decision_counts": {
            "BUY": int((dec or {}).get("buy_n") or 0),
            "SELL": int((dec or {}).get("sell_n") or 0),
            "HOLD": int((dec or {}).get("hold_n") or 0),
            "executed": int((dec or {}).get("executed_n") or 0),
        },
        "state": serial(st),
        "paper_only": True,
    }


@router.post("/b/start")
async def active_b_start(_auth: None = Depends(require_lab_token)):
    from ..main import db, serial

    with db() as c:
        ensure_active_schema(c.execute)
        res = start_bot(c.execute, actor="dashboard")
        c.commit()
    return serial(res)


@router.post("/b/stop")
async def active_b_stop(_auth: None = Depends(require_lab_token)):
    from ..main import db, serial

    with db() as c:
        ensure_active_schema(c.execute)
        res = stop_bot(c.execute, actor="dashboard")
        c.commit()
    return serial(res)


@router.get("/b/decisions")
async def active_b_decisions(
    limit: int = Query(80, ge=1, le=500),
    symbol: str | None = None,
    action: str | None = None,
):
    from ..main import db, serial

    with db() as c:
        ensure_active_schema(c.execute)
        q = """SELECT * FROM active_decisions WHERE account_id=%s"""
        params: list[Any] = [ACCOUNT_B]
        if symbol:
            q += " AND symbol=%s"
            params.append(symbol)
        if action:
            q += " AND action=%s"
            params.append(action.upper())
        q += " ORDER BY id DESC LIMIT %s"
        params.append(limit)
        rows = list(c.execute(q, params))
    return [serial(r) for r in rows]


@router.get("/b/fills")
async def active_b_fills(limit: int = Query(80, ge=1, le=500), symbol: str | None = None):
    from ..main import db, serial

    with db() as c:
        ensure_active_schema(c.execute)
        q = """SELECT * FROM active_trades WHERE account_id=%s"""
        params: list[Any] = [ACCOUNT_B]
        if symbol:
            q += " AND symbol=%s"
            params.append(symbol)
        q += " ORDER BY id DESC LIMIT %s"
        params.append(limit)
        rows = list(c.execute(q, params))
    return [serial(r) for r in rows]


@router.get("/c/status")
async def active_c_status():
    from ..main import db, serial

    with db() as c:
        return serial(validation_report(c.execute))
