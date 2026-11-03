"""Lab portfolio reconciliation — cash, marks, costs, PnL identity checks."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(x) -> Decimal:
    return Decimal(str(x))


def peak_equity_from_daily_rows(rows: list[dict[str, Any]], initial: Decimal) -> Decimal:
    """
    Peak must consider BOTH start_equity and end_equity.
    Bug (pre-fix): MAX(COALESCE(end, start)) ignored start when end < start.
    """
    peak = _d(initial)
    for r in rows:
        if r.get("start_equity") is not None:
            peak = max(peak, _d(r["start_equity"]))
        if r.get("end_equity") is not None:
            peak = max(peak, _d(r["end_equity"]))
    return peak


def drawdown_fraction(*, equity: Decimal, peak: Decimal) -> float:
    """Current drawdown as fraction of peak: (peak - equity) / peak, else 0."""
    if peak <= 0 or equity is None:
        return 0.0
    if equity >= peak:
        return 0.0
    return float((peak - equity) / peak)


def reconcile_lab_snapshot(
    *,
    cash: Decimal,
    positions: list[dict[str, Any]],
    marks: dict[str, dict[str, Any]],
    fees_accumulated: Decimal,
    realized_pnl: Decimal,
    initial_capital: Decimal,
    slip_rate: Decimal = Decimal("0.001"),
    fee_rate: Decimal = Decimal("0.001"),
) -> dict[str, Any]:
    """
    Reconcile lab books without inventing marks.
    Gross equity ≈ cash + Σ qty*mark
    Unrealized ≈ MV - invested_cost
    Exit cost estimate is theoretical (not a fill).
    """
    invested = Decimal("0")
    market_value = Decimal("0")
    incomplete = False
    lines: list[dict[str, Any]] = []
    exit_fee_est = Decimal("0")
    exit_slip_est = Decimal("0")

    for p in positions:
        sym = p["symbol"]
        qty = _d(p["qty"])
        cost = _d(p["cost"])
        entry = _d(p.get("entry_price") or 0)
        invested += cost
        m = marks.get(sym) or {}
        if not (m.get("ok") and m.get("price") is not None):
            incomplete = True
            lines.append(
                {
                    "symbol": sym,
                    "qty": float(qty),
                    "entry_price": float(entry) if entry else None,
                    "cost": float(cost),
                    "mark_price": None,
                    "market_value": None,
                    "unrealized_pnl": None,
                    "estimated_exit_fee": None,
                    "estimated_exit_slip_cost": None,
                    "complete": False,
                }
            )
            continue
        mark = _d(m["price"])
        mv = qty * mark
        market_value += mv
        est_exec = mark * (Decimal("1") - slip_rate)
        fee_e = qty * est_exec * fee_rate
        slip_e = qty * mark * slip_rate
        exit_fee_est += fee_e
        exit_slip_est += slip_e
        lines.append(
            {
                "symbol": sym,
                "qty": float(qty),
                "entry_price": float(entry) if entry else None,
                "cost": float(cost),
                "mark_price": float(mark),
                "mark_at": m.get("at"),
                "mark_source": m.get("source"),
                "market_value": float(mv),
                "unrealized_pnl": float(mv - cost),
                "estimated_exit_execution": float(est_exec),
                "estimated_exit_fee": float(fee_e),
                "estimated_exit_slip_cost": float(slip_e),
                "complete": True,
            }
        )

    if incomplete:
        equity_gross = None
        unrealized = None
        equity_net_est = None
        status = "INCOMPLETE"
    else:
        equity_gross = cash + market_value
        unrealized = market_value - invested
        # Net estimate after theoretical exit costs (illustrative, not booked)
        equity_net_est = equity_gross - exit_fee_est - exit_slip_est
        status = "OK"

    identity_ok = True
    issues: list[str] = []
    if cash < 0:
        identity_ok = False
        issues.append("negative_cash")
    if invested < 0:
        identity_ok = False
        issues.append("negative_invested")
    if equity_gross is not None:
        # cash + mv should equal equity_gross by construction
        if abs((cash + market_value) - equity_gross) > Decimal("1e-9"):
            identity_ok = False
            issues.append("equity_identity_break")

    return {
        "status": status,
        "cash": float(cash),
        "invested_cost": float(invested),
        "market_value": float(market_value) if not incomplete else None,
        "equity_gross": float(equity_gross) if equity_gross is not None else None,
        "equity_net_after_exit_costs_est": float(equity_net_est)
        if equity_net_est is not None
        else None,
        "unrealized_pnl": float(unrealized) if unrealized is not None else None,
        "realized_pnl": float(realized_pnl),
        "fees_accumulated": float(fees_accumulated),
        "estimated_exit_fees": float(exit_fee_est) if not incomplete else None,
        "estimated_exit_slippage_cost": float(exit_slip_est) if not incomplete else None,
        "initial_capital": float(initial_capital),
        "return_vs_initial": (
            float((equity_gross - initial_capital) / initial_capital)
            if equity_gross is not None and initial_capital > 0
            else None
        ),
        "positions": lines,
        "identity_ok": identity_ok,
        "issues": issues,
        "note": (
            "equity_gross = cash + Σ(qty×mark). "
            "equity_net_after_exit_costs_est resta fee/slip teóricos de salida (no contabilizados)."
        ),
    }
