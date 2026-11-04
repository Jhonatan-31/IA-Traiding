"""DEMO control + read APIs — start/stop require LAB_CONTROL_TOKEN."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from ..lab.auth import require_lab_token
from . import ACCOUNT_ID, INITIAL_CASH, POLICY_VERSION
from .control import start_bot, stop_bot
from .policy import POLICY_DOC
from .schema import ensure_demo_schema

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@router.get("/status")
async def demo_status():
    from ..main import db, serial
    import httpx
    from ..ohlcv import fetch_klines

    with db() as c:
        ensure_demo_schema(c.execute)
        acc = c.execute("SELECT * FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
        st = c.execute("SELECT * FROM demo_state WHERE id=1").fetchone()
        positions = list(
            c.execute(
                "SELECT * FROM demo_positions WHERE account_id=%s ORDER BY symbol",
                (ACCOUNT_ID,),
            )
        )
        last_trade = c.execute(
            """SELECT * FROM demo_trades WHERE account_id=%s ORDER BY id DESC LIMIT 1""",
            (ACCOUNT_ID,),
        ).fetchone()
        trade_n = c.execute(
            "SELECT COUNT(*) AS n FROM demo_trades WHERE account_id=%s", (ACCOUNT_ID,)
        ).fetchone()["n"]
        dec = c.execute(
            """SELECT COUNT(*) FILTER (WHERE action='BUY') buy_n,
                      COUNT(*) FILTER (WHERE action='SELL') sell_n,
                      COUNT(*) FILTER (WHERE action='HOLD') hold_n,
                      COUNT(*) FILTER (WHERE executed) executed_n
               FROM demo_decisions WHERE account_id=%s""",
            (ACCOUNT_ID,),
        ).fetchone()
        tc = c.execute(
            """SELECT COUNT(*) FILTER (WHERE side='BUY') buys,
                      COUNT(*) FILTER (WHERE side='SELL') sells,
                      COALESCE(SUM(fee),0) fees,
                      COALESCE(SUM(slip),0) slip,
                      COALESCE(SUM(realized_pnl),0) rpnl
               FROM demo_trades WHERE account_id=%s""",
            (ACCOUNT_ID,),
        ).fetchone()
        last_event = c.execute(
            "SELECT * FROM demo_events ORDER BY id DESC LIMIT 1"
        ).fetchone()

    marks: dict[str, float] = {}
    try:
        async with httpx.AsyncClient(
            timeout=12, headers={"User-Agent": "ResearchPaperBot/demo-status"}
        ) as client:
            for p in positions:
                try:
                    k = await fetch_klines(client, p["symbol"], "1m", limit=5, use_cache=True)
                    closed = [x for x in k["candles"] if x.get("is_closed", True)]
                    if closed:
                        marks[p["symbol"]] = float(closed[-1]["close"])
                except Exception:
                    pass
    except Exception:
        pass

    cash = _f(acc["cash"]) if acc else None
    invested = sum(float(p["cost"]) for p in positions)
    mv = 0.0
    upnl = 0.0
    pos_out = []
    for p in positions:
        m = marks.get(p["symbol"])
        qty = float(p["qty"])
        cost = float(p["cost"])
        mtm = qty * m if m is not None else None
        if mtm is not None:
            mv += mtm
            upnl += mtm - cost
        pos_out.append(
            {
                "symbol": p["symbol"],
                "qty": qty,
                "cost": cost,
                "entry_price": _f(p["entry_price"]),
                "mark": m,
                "mtm": mtm,
                "upnl": (mtm - cost) if mtm is not None else None,
            }
        )
    equity = (cash or 0) + mv if cash is not None else None
    peak = _f(acc["peak_equity"]) if acc else None
    dd = None
    if equity is not None and peak and peak > 0:
        dd = (equity - peak) / peak

    return serial(
        {
            "mode": "PAPER_ONLY",
            "account_id": ACCOUNT_ID,
            "policy_version": POLICY_VERSION,
            "policy_doc": POLICY_DOC,
            "probability_validated": False,
            "bot_status": (st or {}).get("status"),
            "state": st,
            "cash": cash,
            "initial_capital": INITIAL_CASH,
            "invested_cost": invested,
            "equity": equity,
            "unrealized_pnl": upnl,
            "realized_pnl": _f(tc["rpnl"]),
            "fees": _f(tc["fees"]),
            "slip": _f(tc["slip"]),
            "peak_equity": peak,
            "drawdown_vs_peak": dd,
            "positions": pos_out,
            "decision_counts": {
                "BUY": int(dec["buy_n"]),
                "SELL": int(dec["sell_n"]),
                "HOLD": int(dec["hold_n"]),
                "executed": int(dec["executed_n"]),
            },
            "trade_counts": {"buys": int(tc["buys"]), "sells": int(tc["sells"]), "total": int(trade_n)},
            "last_trade": last_trade,
            "last_event": last_event,
            "now_utc": datetime.now(timezone.utc).isoformat(),
            "integrity": {
                "isolated": True,
                "paper_only": True,
                "does_not_touch_other_ledgers": True,
            },
        }
    )


@router.post("/start")
def demo_start(_auth: str = Depends(require_lab_token)):
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        out = start_bot(c.execute, actor="dashboard")
    return serial(out)


@router.post("/stop")
def demo_stop(_auth: str = Depends(require_lab_token)):
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        out = stop_bot(c.execute, actor="dashboard")
    return serial(out)


@router.get("/decisions")
def demo_decisions(
    limit: int = Query(100, ge=1, le=500),
    symbol: str | None = None,
    action: str | None = None,
):
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        q = """SELECT * FROM demo_decisions WHERE account_id=%s"""
        args: list[Any] = [ACCOUNT_ID]
        if symbol:
            q += " AND symbol=%s"
            args.append(symbol.upper())
        if action:
            q += " AND action=%s"
            args.append(action.upper())
        q += " ORDER BY id DESC LIMIT %s"
        args.append(limit)
        rows = list(c.execute(q, tuple(args)))
    return serial(rows)


@router.get("/orders")
def demo_orders(limit: int = Query(100, ge=1, le=500)):
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        rows = list(
            c.execute(
                """SELECT * FROM demo_orders WHERE account_id=%s ORDER BY id DESC LIMIT %s""",
                (ACCOUNT_ID, limit),
            )
        )
    return serial(rows)


@router.get("/fills")
def demo_fills(
    limit: int = Query(100, ge=1, le=500),
    symbol: str | None = None,
):
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        q = "SELECT * FROM demo_trades WHERE account_id=%s"
        args: list[Any] = [ACCOUNT_ID]
        if symbol:
            q += " AND symbol=%s"
            args.append(symbol.upper())
        q += " ORDER BY id DESC LIMIT %s"
        args.append(limit)
        rows = list(c.execute(q, tuple(args)))
    return serial(rows)


@router.get("/positions")
def demo_positions():
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        rows = list(
            c.execute(
                "SELECT * FROM demo_positions WHERE account_id=%s ORDER BY symbol",
                (ACCOUNT_ID,),
            )
        )
    return serial(rows)


@router.get("/performance")
def demo_performance():
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        acc = c.execute("SELECT * FROM demo_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
        ticks = list(
            c.execute(
                "SELECT at, equity, cash, invested FROM demo_equity_ticks ORDER BY id DESC LIMIT 200"
            )
        )
        gaps = c.execute("SELECT coverage_gap_json FROM demo_state WHERE id=1").fetchone()
        events = list(c.execute("SELECT * FROM demo_events ORDER BY id DESC LIMIT 50"))
    return serial(
        {
            "account": acc,
            "equity_ticks": list(reversed(ticks)),
            "coverage_gaps": (gaps or {}).get("coverage_gap_json") or [],
            "events": events,
            "policy_version": POLICY_VERSION,
            "note": "Experimental DEMO — not a statistical edge claim.",
        }
    )


@router.get("/markers")
def demo_markers(symbol: str = Query(...), limit: int = Query(80, ge=1, le=300)):
    """Chart markers for DEMO fills only — never mixed with other ledgers."""
    from ..main import db, serial

    with db() as c:
        ensure_demo_schema(c.execute)
        rows = list(
            c.execute(
                """SELECT id, at, symbol, side, qty, price, fee, slip, realized_pnl, reason, correlation_id
                   FROM demo_trades WHERE account_id=%s AND symbol=%s
                   ORDER BY id DESC LIMIT %s""",
                (ACCOUNT_ID, symbol.upper(), limit),
            )
        )
    markers = []
    for r in reversed(rows):
        markers.append(
            {
                "time": int(r["at"].timestamp()) if hasattr(r["at"], "timestamp") else None,
                "at": r["at"],
                "position": "belowBar" if r["side"] == "BUY" else "aboveBar",
                "color": "#16a34a" if r["side"] == "BUY" else "#dc2626",
                "shape": "arrowUp" if r["side"] == "BUY" else "arrowDown",
                "text": f"{r['side']} {r['reason']}",
                "side": r["side"],
                "price": _f(r["price"]),
                "qty": _f(r["qty"]),
                "fee": _f(r["fee"]),
                "pnl": _f(r["realized_pnl"]),
                "reason": r["reason"],
                "id": r["id"],
                "ledger": "demo_manual_control",
            }
        )
    return serial({"symbol": symbol.upper(), "markers": markers, "ledger": ACCOUNT_ID})
