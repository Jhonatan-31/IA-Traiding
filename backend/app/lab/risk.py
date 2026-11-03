"""Lab risk gates and lab-local circuit breaker — never enables real trading."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from . import AUTHORIZED_STRATEGY
from .config import (
    ACCOUNT_ID,
    MAX_DAILY_LOSS_PCT,
    MAX_DRAWDOWN_PCT,
    MAX_POSITIONS,
    PRICE_STALE_S,
)


def _d(x) -> Decimal:
    return Decimal(str(x))


def lab_equity(execute: Callable, marks: dict[str, Decimal] | None = None) -> dict[str, Any]:
    acc = execute("SELECT * FROM lab_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
    positions = list(
        execute("SELECT * FROM lab_positions WHERE account_id=%s", (ACCOUNT_ID,))
    )
    cash = _d(acc["cash"])
    invested = sum((_d(p["cost"]) for p in positions), Decimal("0"))
    mtm = cash
    missing_marks = 0
    for p in positions:
        sym = p["symbol"]
        if marks and sym in marks:
            mtm += _d(p["qty"]) * marks[sym]
        else:
            missing_marks += 1
            mtm += _d(p["cost"])  # fallback cost basis
    return {
        "cash": cash,
        "invested_cost": invested,
        "equity": mtm,
        "positions_n": len(positions),
        "missing_marks": missing_marks,
        "initial_capital": _d(acc["initial_capital"]),
    }


def ensure_daily_equity(execute: Callable, equity: Decimal) -> Decimal:
    today = date.today()
    row = execute(
        "SELECT start_equity FROM lab_equity_daily WHERE account_id=%s AND day=%s",
        (ACCOUNT_ID, today),
    ).fetchone()
    if row:
        return _d(row["start_equity"])
    execute(
        """INSERT INTO lab_equity_daily(account_id, day, start_equity, end_equity)
           VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
        (ACCOUNT_ID, today, equity, equity),
    )
    return equity


def evaluate_lab_breaker(
    execute: Callable,
    *,
    equity: Decimal,
    day_start_equity: Decimal,
    peak_equity: Decimal,
    data_age_s: float | None,
    binance_ok: bool,
    postgres_ok: bool = True,
    accounting_ok: bool = True,
    duplicate_detected: bool = False,
    strategy: str = AUTHORIZED_STRATEGY,
) -> tuple[bool, str | None]:
    if not postgres_ok:
        return True, "postgres_unreachable"
    if not accounting_ok:
        return True, "accounting_error"
    if duplicate_detected:
        return True, "duplicate_orders"
    if strategy != AUTHORIZED_STRATEGY:
        return True, "unauthorized_strategy"
    if not binance_ok:
        return True, "binance_failure"
    if data_age_s is not None and data_age_s > PRICE_STALE_S:
        return True, "stale_market_data"
    if day_start_equity > 0:
        daily_loss = (day_start_equity - equity) / day_start_equity
        if daily_loss >= MAX_DAILY_LOSS_PCT:
            return True, "max_daily_loss"
    if peak_equity > 0:
        dd = (peak_equity - equity) / peak_equity
        if dd >= MAX_DRAWDOWN_PCT:
            return True, "max_drawdown"
    eq = lab_equity(execute)
    if eq["positions_n"] > MAX_POSITIONS:
        return True, "excessive_exposure"
    return False, None


def persist_lab_breaker(
    execute: Callable,
    active: bool,
    reason: str | None,
    *,
    evidence: dict | None = None,
) -> None:
    import json

    prev = execute(
        "SELECT breaker_active, breaker_reason FROM lab_executor_state WHERE id=1"
    ).fetchone()
    execute(
        """UPDATE lab_executor_state SET
             breaker_active=%s, breaker_reason=%s, updated_at=NOW() WHERE id=1""",
        (active, reason),
    )
    changed = (not prev) or bool(prev.get("breaker_active")) != bool(active) or (
        active and (prev or {}).get("breaker_reason") != reason
    )
    if changed:
        execute(
            """INSERT INTO lab_breaker_events(active, reason, evidence_json)
               VALUES(%s,%s,%s::jsonb)""",
            (active, reason, json.dumps(evidence or {})),
        )


def critical_condition_still_active(execute: Callable) -> tuple[bool, str | None]:
    """Used on resume — do not clear pause/breaker while critical reason persists."""
    state = execute("SELECT * FROM lab_executor_state WHERE id=1").fetchone()
    if state and state.get("breaker_active"):
        return True, state.get("breaker_reason") or "breaker_active"
    if not accounting_ok(execute):
        return True, "accounting_error"
    return False, None


def can_buy(
    *,
    paused: bool,
    breaker_active: bool,
    cash: Decimal,
    budget: Decimal,
    positions_n: int,
    max_positions: int,
    symbol_valid: bool,
    data_fresh: bool,
    liquidity_ok: bool,
    fill_ok: bool,
    strategy: str,
) -> tuple[bool, str]:
    if paused:
        return False, "executor_paused"
    if breaker_active:
        return False, "circuit_breaker"
    if strategy != AUTHORIZED_STRATEGY:
        return False, "unauthorized_strategy"
    if not symbol_valid:
        return False, "invalid_spot_symbol"
    if not data_fresh:
        return False, "stale_market_data"
    if not liquidity_ok:
        return False, "insufficient_liquidity"
    if not fill_ok:
        return False, "no_executable_price"
    if positions_n >= max_positions:
        return False, "max_positions"
    if budget > cash:
        return False, "insufficient_cash"
    return True, "ok"


def accounting_ok(execute: Callable) -> bool:
    acc = execute("SELECT cash FROM lab_accounts WHERE id=%s", (ACCOUNT_ID,)).fetchone()
    if not acc or _d(acc["cash"]) < 0:
        return False
    bad = execute(
        """SELECT 1 FROM lab_positions
           WHERE account_id=%s AND (qty<=0 OR cost<0) LIMIT 1""",
        (ACCOUNT_ID,),
    ).fetchone()
    return bad is None
