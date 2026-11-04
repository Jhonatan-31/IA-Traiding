"""Express dashboard API — read-only status + final report helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from . import ACCOUNT_ID, INITIAL_CASH
from .policy import END_UTC, POLICY_DOC, POLICY_VERSION, is_ended, seconds_remaining
from .schema import ensure_express_schema

router = APIRouter(prefix="/api/express", tags=["express"])


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@router.get("/status")
async def express_status():
    from ..main import db, serial
    from ..ohlcv import fetch_klines
    import httpx

    with db() as c:
        ensure_express_schema(c.execute)
        acc = c.execute(
            "SELECT * FROM express_accounts WHERE id=%s", (ACCOUNT_ID,)
        ).fetchone()
        st = c.execute("SELECT * FROM express_state WHERE id=1").fetchone()
        positions = list(
            c.execute(
                "SELECT * FROM express_positions WHERE account_id=%s ORDER BY symbol",
                (ACCOUNT_ID,),
            )
        )
        decisions = list(
            c.execute(
                """SELECT id, at, symbol, action, observed_price, signal_score,
                          probability_validated, probability, reason, candle_1m_ms
                   FROM express_decisions WHERE account_id=%s
                   ORDER BY id DESC LIMIT 40""",
                (ACCOUNT_ID,),
            )
        )
        rejects = list(
            c.execute(
                "SELECT id, at, symbol, reason FROM express_rejects ORDER BY id DESC LIMIT 30"
            )
        )
        trades = list(
            c.execute(
                """SELECT * FROM express_trades WHERE account_id=%s ORDER BY id DESC LIMIT 40""",
                (ACCOUNT_ID,),
            )
        )
        counts = c.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE action='BUY') AS buy_n,
                 COUNT(*) FILTER (WHERE action='SELL') AS sell_n,
                 COUNT(*) FILTER (WHERE action='HOLD') AS hold_n
               FROM express_decisions WHERE account_id=%s""",
            (ACCOUNT_ID,),
        ).fetchone()
        trade_counts = c.execute(
            """SELECT
                 COUNT(*) FILTER (WHERE side='BUY') AS buys,
                 COUNT(*) FILTER (WHERE side='SELL') AS sells,
                 COALESCE(SUM(fee),0) AS fees,
                 COALESCE(SUM(slip),0) AS slip,
                 COALESCE(SUM(realized_pnl),0) AS rpnl
               FROM express_trades WHERE account_id=%s""",
            (ACCOUNT_ID,),
        ).fetchone()

    marks: dict[str, float] = {}
    try:
        async with httpx.AsyncClient(
            timeout=15, headers={"User-Agent": "ResearchPaperBot/express-status"}
        ) as client:
            for p in positions:
                try:
                    k = await fetch_klines(
                        client, p["symbol"], "1m", limit=5, use_cache=True
                    )
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
    # Hypothetical liquidation net of sell costs
    liq_fee = mv * 0.001
    liq_slip = mv * 0.0005
    equity_net_if_flat = (cash or 0) + mv - liq_fee - liq_slip if cash is not None else None

    now = datetime.now(timezone.utc)
    return serial(
        {
            "mode": "PAPER_ONLY",
            "account_id": ACCOUNT_ID,
            "policy_version": POLICY_VERSION,
            "policy_doc": POLICY_DOC,
            "probability_validated": False,
            "probability_note": "No calibrated model for express; signal_score is not a probability.",
            "deadline_utc": END_UTC.isoformat(),
            "now_utc": now.isoformat(),
            "seconds_remaining": seconds_remaining(now),
            "ended": is_ended(now) or (st or {}).get("status") == "ENDED",
            "state": st,
            "cash": cash,
            "initial_capital": INITIAL_CASH,
            "invested_cost": invested,
            "equity_gross": equity,
            "unrealized_pnl": upnl,
            "realized_pnl": _f(trade_counts["rpnl"]),
            "fees": _f(trade_counts["fees"]),
            "slip": _f(trade_counts["slip"]),
            "peak_equity": _f(acc["peak_equity"]) if acc else None,
            "equity_net_if_liquidate_est": equity_net_if_flat,
            "liquidation_note": "Hypothetical close at last marks minus fee/slip — not an executed sale.",
            "positions": pos_out,
            "decision_counts": {
                "BUY": int(counts["buy_n"]),
                "SELL": int(counts["sell_n"]),
                "HOLD": int(counts["hold_n"]),
            },
            "trade_counts": {
                "buys": int(trade_counts["buys"]),
                "sells": int(trade_counts["sells"]),
            },
            "decisions": decisions,
            "rejects": rejects,
            "trades": trades,
            "integrity": {
                "isolated_ledger": True,
                "does_not_touch_sma_lab_research": True,
                "paper_only": True,
            },
        }
    )


@router.get("/report")
async def express_report():
    status = await express_status()
    # Attach coverage from state
    st = status.get("state") or {}
    started = st.get("started_at")
    ended = st.get("ended_at") or (status.get("deadline_utc") if status.get("ended") else None)
    return {
        **status,
        "report_type": "express_functional_test",
        "statistical_edge_claim": False,
        "disclaimer": (
            "Prueba funcional exploratoria de corta duración. "
            "No valida ventaja económica de la estrategia."
        ),
        "coverage": {
            "started_at": started,
            "ended_at": ended,
            "cycle_count": st.get("cycle_count"),
            "status": st.get("status"),
        },
    }
