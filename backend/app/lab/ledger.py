"""Lab ledger mutations — isolated from SMA paper and research_sim."""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Callable

from .config import ACCOUNT_ID, FEE_RATE, SLIP_RATE, STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_HOLD_BARS


def _d(x) -> Decimal:
    return Decimal(str(x))


def snapshot(execute: Callable) -> dict[str, Any]:
    acc = execute("SELECT * FROM lab_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
    positions = list(
        execute(
            "SELECT * FROM lab_positions WHERE account_id=%s ORDER BY symbol",
            (ACCOUNT_ID,),
        )
    )
    invested = sum((_d(p["cost"]) for p in positions), Decimal("0"))
    cash = _d(acc["cash"])
    return {
        "account_id": ACCOUNT_ID,
        "cash": float(cash),
        "invested_cost": float(invested),
        "equity_cost_basis": float(cash + invested),
        "initial_capital": float(_d(acc["initial_capital"])),
        "positions": [dict(p) for p in positions],
        "separated_from_sma_paper": True,
        "separated_from_research_sim": True,
    }


def apply_buy(
    execute: Callable,
    *,
    order_uid: str,
    symbol: str,
    budget: Decimal,
    fill_price: Decimal,
    candle_ms: int,
    strategy: str,
    reason: str,
    fee: Decimal | None = None,
    slip: Decimal | None = None,
) -> dict[str, Any]:
    acc = execute("SELECT cash FROM lab_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
    cash = _d(acc["cash"])
    fee = fee if fee is not None else fill_price * FEE_RATE * (budget / fill_price)
    # budget includes fee+notional; qty from (budget)/(price) after slip already in fill_price
    if budget > cash or fill_price <= 0:
        return {"status": "REJECTED", "reason": "insufficient_cash_or_price"}
    qty = budget / fill_price
    fee_amt = budget * FEE_RATE
    slip_amt = budget * SLIP_RATE if slip is None else slip
    # Use budget as cash outlay (same pattern as SMA paper)
    new_cash = cash - budget
    if new_cash < 0:
        return {"status": "REJECTED", "reason": "insufficient_cash"}
    execute("UPDATE lab_accounts SET cash=%s WHERE id=%s", (new_cash, ACCOUNT_ID))
    existing = execute(
        "SELECT * FROM lab_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_ID, symbol),
    ).fetchone()
    if existing:
        return {"status": "REJECTED", "reason": "position_already_open"}
    execute(
        """INSERT INTO lab_positions(
            account_id, symbol, qty, cost, entry_price, opened_candle_ms,
            stop_loss_pct, take_profit_pct, max_hold_bars)
           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            ACCOUNT_ID,
            symbol,
            qty,
            budget,
            fill_price,
            candle_ms,
            STOP_LOSS_PCT,
            TAKE_PROFIT_PCT,
            MAX_HOLD_BARS,
        ),
    )
    execute(
        """INSERT INTO lab_trades(
            account_id, order_uid, symbol, side, qty, price, fee, slip,
            candle_ms, strategy, reason)
           VALUES(%s,%s::uuid,%s,'BUY',%s,%s,%s,%s,%s,%s,%s)""",
        (
            ACCOUNT_ID,
            order_uid,
            symbol,
            qty,
            fill_price,
            fee_amt,
            slip_amt,
            candle_ms,
            strategy,
            reason,
        ),
    )
    return {
        "status": "FILLED",
        "qty": float(qty),
        "cash_after": float(new_cash),
        "fee": float(fee_amt),
        "slip": float(slip_amt),
    }


def apply_sell(
    execute: Callable,
    *,
    order_uid: str,
    symbol: str,
    fill_price: Decimal,
    candle_ms: int,
    strategy: str,
    reason: str,
    stop_triggered: bool = False,
    stop_trigger_price: Decimal | None = None,
) -> dict[str, Any]:
    pos = execute(
        "SELECT * FROM lab_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_ID, symbol),
    ).fetchone()
    if not pos:
        return {"status": "REJECTED", "reason": "no_position"}
    if fill_price <= 0:
        return {"status": "REJECTED", "reason": "invalid_price"}
    qty = _d(pos["qty"])
    cost = _d(pos["cost"])
    proceeds = qty * fill_price
    fee_amt = proceeds * FEE_RATE
    net = proceeds - fee_amt
    realized = net - cost
    acc = execute("SELECT cash FROM lab_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
    new_cash = _d(acc["cash"]) + net
    execute("UPDATE lab_accounts SET cash=%s WHERE id=%s", (new_cash, ACCOUNT_ID))
    execute(
        "DELETE FROM lab_positions WHERE account_id=%s AND symbol=%s",
        (ACCOUNT_ID, symbol),
    )
    execute(
        """INSERT INTO lab_trades(
            account_id, order_uid, symbol, side, qty, price, fee, slip,
            candle_ms, strategy, reason, realized_pnl)
           VALUES(%s,%s::uuid,%s,'SELL',%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            ACCOUNT_ID,
            order_uid,
            symbol,
            qty,
            fill_price,
            fee_amt,
            proceeds * SLIP_RATE,
            candle_ms,
            strategy,
            reason,
            realized,
        ),
    )
    return {
        "status": "FILLED",
        "qty": float(qty),
        "cash_after": float(new_cash),
        "realized_pnl": float(realized),
        "fee": float(fee_amt),
        "stop_triggered": stop_triggered,
        "stop_trigger_price": float(stop_trigger_price) if stop_trigger_price is not None else None,
        "execution_price": float(fill_price),
    }


def new_order_uid() -> str:
    return str(uuid.uuid4())
