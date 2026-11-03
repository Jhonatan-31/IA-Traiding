"""Mark-to-market lab portfolio — never invents missing marks."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import httpx

from .config import ACCOUNT_ID


def _d(x) -> Decimal:
    return Decimal(str(x))


async def fetch_marks(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Return symbol → {price, source, at, ok} from public ticker. Missing = incomplete."""
    out: dict[str, dict[str, Any]] = {}
    if not symbols:
        return out
    now = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(
        timeout=15, headers={"User-Agent": "ResearchPaperBot/lab-mtm"}
    ) as client:
        try:
            r = await client.get("https://data-api.binance.vision/api/v3/ticker/price")
            r.raise_for_status()
            lookup = {x["symbol"]: Decimal(str(x["price"])) for x in r.json()}
            for sym in symbols:
                if sym in lookup and lookup[sym] > 0:
                    out[sym] = {
                        "price": float(lookup[sym]),
                        "source": "binance_public_ticker",
                        "at": now,
                        "ok": True,
                    }
                else:
                    out[sym] = {
                        "price": None,
                        "source": None,
                        "at": None,
                        "ok": False,
                        "reason": "mark_missing",
                    }
        except Exception as exc:
            for sym in symbols:
                out[sym] = {
                    "price": None,
                    "source": None,
                    "at": None,
                    "ok": False,
                    "reason": f"fetch_error:{type(exc).__name__}",
                }
    return out


def portfolio_valuation(
    execute: Callable,
    marks: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    acc = execute("SELECT * FROM lab_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
    positions = list(
        execute("SELECT * FROM lab_positions WHERE account_id=%s", (ACCOUNT_ID,))
    )
    trades = list(
        execute(
            "SELECT fee, realized_pnl, side FROM lab_trades WHERE account_id=%s",
            (ACCOUNT_ID,),
        )
    )
    cash = _d(acc["cash"])
    initial = _d(acc["initial_capital"])
    invested = sum((_d(p["cost"]) for p in positions), Decimal("0"))
    fees = sum((_d(t["fee"] or 0) for t in trades), Decimal("0"))
    realized = sum(
        (_d(t["realized_pnl"]) for t in trades if t.get("realized_pnl") is not None),
        Decimal("0"),
    )

    marks = marks or {}
    pos_rows = []
    market_value = Decimal("0")
    incomplete = False
    for p in positions:
        sym = p["symbol"]
        m = marks.get(sym) or {}
        qty = _d(p["qty"])
        cost = _d(p["cost"])
        entry = _d(p["entry_price"] or 0)
        if m.get("ok") and m.get("price") is not None:
            px = _d(m["price"])
            mv = qty * px
            upnl = mv - cost
            market_value += mv
            pos_rows.append(
                {
                    "symbol": sym,
                    "qty": float(qty),
                    "cost": float(cost),
                    "entry_price": float(entry) if entry else None,
                    "mark_price": float(px),
                    "mark_source": m.get("source"),
                    "mark_at": m.get("at"),
                    "market_value": float(mv),
                    "unrealized_pnl": float(upnl),
                    "complete": True,
                }
            )
        else:
            incomplete = True
            pos_rows.append(
                {
                    "symbol": sym,
                    "qty": float(qty),
                    "cost": float(cost),
                    "entry_price": float(entry) if entry else None,
                    "mark_price": None,
                    "mark_source": None,
                    "mark_at": None,
                    "market_value": None,
                    "unrealized_pnl": None,
                    "complete": False,
                    "reason": m.get("reason") or "mark_unavailable",
                }
            )

    if positions and incomplete:
        equity = None
        unrealized = None
        valuation_status = "INCOMPLETE"
    elif not positions:
        equity = cash
        unrealized = Decimal("0")
        valuation_status = "OK"
        market_value = Decimal("0")
    else:
        equity = cash + market_value
        unrealized = market_value - invested
        valuation_status = "OK"

    ret = None
    if equity is not None and initial > 0:
        ret = float((equity - initial) / initial)

    # Drawdown vs peak from daily equity table if available
    peak_row = execute(
        """SELECT MAX(COALESCE(end_equity, start_equity)) AS peak
           FROM lab_equity_daily WHERE account_id=%s""",
        (ACCOUNT_ID,),
    ).fetchone()
    peak = _d(peak_row["peak"]) if peak_row and peak_row["peak"] is not None else initial
    if equity is not None and peak > 0:
        drawdown = float((peak - equity) / peak) if equity < peak else 0.0
    else:
        drawdown = None

    from .positions_audit import enrich_positions

    # Merge raw exit fields (sl/tp %) onto MTM rows before enrich
    raw_by_sym = {p["symbol"]: dict(p) for p in positions}
    for row in pos_rows:
        raw = raw_by_sym.get(row["symbol"]) or {}
        row.setdefault("stop_loss_pct", raw.get("stop_loss_pct"))
        row.setdefault("take_profit_pct", raw.get("take_profit_pct"))
        row.setdefault("max_hold_bars", raw.get("max_hold_bars"))
        row.setdefault("opened_at", raw.get("opened_at"))
        row.setdefault("opened_candle_ms", raw.get("opened_candle_ms"))
        row.setdefault("qty", row.get("qty"))
    enriched = enrich_positions(pos_rows, marks)

    return {
        "valuation_status": valuation_status,
        "cash": float(cash),
        "invested_cost": float(invested),
        "market_value_positions": float(market_value) if not incomplete or not positions else None,
        "equity_estimate": float(equity) if equity is not None else None,
        "realized_pnl": float(realized),
        "unrealized_pnl": float(unrealized) if unrealized is not None else None,
        "fees_accumulated": float(fees),
        "return_vs_initial": ret,
        "drawdown_vs_peak": drawdown,
        "peak_equity": float(peak),
        "initial_capital": float(initial),
        "positions": enriched,
        "note": (
            "Valoración incompleta: faltan precios válidos; no se inventan marks."
            if valuation_status == "INCOMPLETE"
            else "MTM con ticker público Binance; fees/slip ya embebidos en fills. "
            "Mark observado ≠ precio de ejecución simulado."
        ),
    }
