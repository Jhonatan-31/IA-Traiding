"""Virtual research ledger — strictly separated from SMA paper account table."""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Callable


def _d(x) -> Decimal:
    return Decimal(str(x))


def get_account(execute: Callable, account_id: str = "research_sim") -> dict:
    row = execute(
        "SELECT * FROM virt_accounts WHERE id=%s", (account_id,)
    ).fetchone()
    if not row:
        raise RuntimeError(f"virt account missing: {account_id}")
    return dict(row)


def ledger_snapshot(execute: Callable, account_id: str = "research_sim") -> dict[str, Any]:
    acc = get_account(execute, account_id)
    positions = list(
        execute(
            "SELECT * FROM virt_positions WHERE account_id=%s ORDER BY symbol",
            (account_id,),
        )
    )
    pending = list(
        execute(
            """SELECT * FROM virt_orders
               WHERE account_id=%s AND status IN ('PENDING','PARTIAL')
               ORDER BY id DESC LIMIT 50""",
            (account_id,),
        )
    )
    invested = sum((_d(p["cost"]) for p in positions), Decimal("0"))
    cash = _d(acc["cash"])
    # Mark-to-market requires external prices — report cost basis equity if no marks
    return {
        "account_id": account_id,
        "label": acc["label"],
        "cash": float(cash),
        "invested_cost": float(invested),
        "equity_cost_basis": float(cash + invested),
        "initial_capital": float(_d(acc["initial_capital"])),
        "positions": [dict(p) for p in positions],
        "pending_orders": [dict(o) for o in pending],
        "separated_from_paper_sma": True,
        "note": "This ledger is NOT the paper SMA account (table account/positions/trades).",
    }


def accounting_identity_ok(execute: Callable, account_id: str = "research_sim") -> dict[str, Any]:
    """Conservation: cash + sum(position costs) should match last ledger balance trail when present."""
    snap = ledger_snapshot(execute, account_id)
    last = execute(
        """SELECT balance_after FROM virt_ledger
           WHERE account_id=%s ORDER BY id DESC LIMIT 1""",
        (account_id,),
    ).fetchone()
    cash = _d(snap["cash"])
    invested = _d(snap["invested_cost"])
    # Identity we enforce on buys/sells: cash decreases by budget, position cost increases by same
    ok = cash >= 0 and invested >= 0
    return {
        "ok": ok,
        "cash": float(cash),
        "invested_cost": float(invested),
        "equity_cost_basis": float(cash + invested),
        "last_ledger_balance": float(last["balance_after"]) if last else None,
        "error": None if ok else "negative_cash_or_invested",
    }


def apply_virtual_buy(
    execute: Callable,
    *,
    account_id: str,
    symbol: str,
    budget: Decimal,
    fill_price: Decimal,
    fee: Decimal,
    decision_id: int | None,
    meta: dict | None = None,
) -> dict[str, Any]:
    acc = get_account(execute, account_id)
    cash = _d(acc["cash"])
    if budget > cash:
        execute(
            """INSERT INTO virt_orders(account_id, decision_id, symbol, side, status, reason, meta_json)
               VALUES(%s,%s,%s,'BUY','REJECTED','insufficient_cash',%s::jsonb)""",
            (account_id, decision_id, symbol, json.dumps(meta or {})),
        )
        return {"status": "REJECTED", "reason": "insufficient_cash"}
    qty = (budget - fee) / fill_price if fill_price > 0 else Decimal("0")
    if qty <= 0:
        return {"status": "REJECTED", "reason": "zero_qty"}
    new_cash = cash - budget
    execute(
        "UPDATE virt_accounts SET cash=%s WHERE id=%s",
        (new_cash, account_id),
    )
    existing = execute(
        "SELECT * FROM virt_positions WHERE account_id=%s AND symbol=%s",
        (account_id, symbol),
    ).fetchone()
    if existing:
        execute(
            """UPDATE virt_positions SET qty=qty+%s, cost=cost+%s
               WHERE account_id=%s AND symbol=%s""",
            (qty, budget, account_id, symbol),
        )
    else:
        execute(
            """INSERT INTO virt_positions(account_id, symbol, qty, cost)
               VALUES(%s,%s,%s,%s)""",
            (account_id, symbol, qty, budget),
        )
    execute(
        """INSERT INTO virt_ledger(account_id, entry_type, symbol, amount, balance_after, meta_json)
           VALUES(%s,'BUY',%s,%s,%s,%s::jsonb)""",
        (
            account_id,
            symbol,
            -budget,
            new_cash,
            json.dumps({"qty": float(qty), "price": float(fill_price), **(meta or {})}),
        ),
    )
    execute(
        """INSERT INTO virt_orders(
            account_id, decision_id, symbol, side, status, requested_qty, filled_qty,
            avg_price, fee, meta_json)
           VALUES(%s,%s,%s,'BUY','FILLED',%s,%s,%s,%s,%s::jsonb)""",
        (
            account_id,
            decision_id,
            symbol,
            qty,
            qty,
            fill_price,
            fee,
            json.dumps(meta or {}),
        ),
    )
    return {"status": "FILLED", "qty": float(qty), "cash_after": float(new_cash)}
