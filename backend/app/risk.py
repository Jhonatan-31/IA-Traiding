"""Paper-risk metrics from persisted simulation data — no invented numbers."""
from __future__ import annotations

from decimal import Decimal
from typing import Any


def _d(x) -> Decimal:
    if x is None:
        return Decimal("0")
    return Decimal(str(x))


def realized_pnl_and_fees(trades: list[dict]) -> dict[str, Decimal]:
    """Match FIFO buys/sells per symbol. Fees estimated from fee_rate or 0.001."""
    lots: dict[str, list[dict]] = {}
    realized = Decimal("0")
    fees = Decimal("0")
    closed_trades = 0
    for t in sorted(trades, key=lambda r: r["id"]):
        sym = t["symbol"]
        side = t["side"]
        qty = _d(t["qty"])
        price = _d(t["price"])
        fee_rate = _d(t["fee_rate"]) if t.get("fee_rate") is not None else Decimal("0.001")
        notional = qty * price
        fees += notional * fee_rate
        if side == "BUY":
            lots.setdefault(sym, []).append({"qty": qty, "price": price, "cost": notional})
        elif side == "SELL":
            remaining = qty
            proceeds = notional
            cost_basis = Decimal("0")
            queue = lots.setdefault(sym, [])
            while remaining > 0 and queue:
                lot = queue[0]
                take = min(remaining, lot["qty"])
                cost_basis += take * lot["price"]
                lot["qty"] -= take
                remaining -= take
                if lot["qty"] <= 0:
                    queue.pop(0)
            # If unmatched sell qty remains, only count matched portion
            matched = qty - remaining
            if matched > 0:
                realized += (matched / qty) * proceeds - cost_basis
                closed_trades += 1
    return {
        "realized_pnl": realized,
        "fees_estimated": fees,
        "closed_roundtrips": Decimal(closed_trades),
    }


def equity_drawdown(equities: list[Decimal | float | None]) -> dict[str, float | None]:
    series = [float(x) for x in equities if x is not None]
    if not series:
        return {
            "current_drawdown_pct": None,
            "max_drawdown_pct": None,
            "peak_equity": None,
            "points": 0,
        }
    peak = series[0]
    max_dd = 0.0
    for e in series:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (e - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd
    current_peak = max(series)
    current_dd = (
        (series[-1] - current_peak) / current_peak * 100 if current_peak else None
    )
    return {
        "current_drawdown_pct": current_dd,
        "max_drawdown_pct": max_dd,
        "peak_equity": current_peak,
        "points": len(series),
    }


def build_risk_report(
    *,
    cash: Decimal,
    positions: list[dict],
    trades: list[dict],
    scans: list[dict],
    initial_capital: Decimal,
    limits: dict[str, Any],
) -> dict[str, Any]:
    invested = sum((_d(p["cost"]) for p in positions), Decimal("0"))
    mv = Decimal("0")
    exposure = []
    missing_marks = 0
    for p in positions:
        price = p.get("price")
        if price is None:
            missing_marks += 1
            mark = None
            mval = None
            upnl = None
        else:
            mark = _d(price)
            mval = _d(p["qty"]) * mark
            mv += mval
            upnl = mval - _d(p["cost"])
        exposure.append(
            {
                "symbol": p["symbol"],
                "cost": float(_d(p["cost"])),
                "qty": float(_d(p["qty"])),
                "mark_price": float(mark) if mark is not None else None,
                "market_value": float(mval) if mval is not None else None,
                "unrealized_pnl": float(upnl) if upnl is not None else None,
                "price_source": p.get("price_source") or p.get("source"),
                "valuation": "observed_mark" if mark is not None else "unavailable",
            }
        )

    pnl_pack = realized_pnl_and_fees(trades)
    equity = cash + mv if missing_marks == 0 else None
    equities = [_d(s["equity"]) for s in scans if s.get("equity") is not None]
    dd = equity_drawdown(equities)

    total_exposure_pct = (
        float(invested / initial_capital * 100) if initial_capital else None
    )
    unrealized = float(mv - invested) if missing_marks == 0 else None

    # Daily loss from scans today vs start-of-day equity if available
    daily_loss_pct = None
    if equities:
        day_start = float(equities[0])
        last = float(equities[-1])
        if day_start:
            daily_loss_pct = (last - day_start) / day_start * 100

    breaches = []
    max_exp = float(limits.get("max_exposure_pct", 80))
    max_dd = float(limits.get("max_drawdown_pct", 15))
    max_daily = float(limits.get("max_daily_loss_pct", 5))
    max_pos = int(limits.get("max_positions", 10))
    max_trades_day = int(limits.get("max_trades_per_day", 50))

    if total_exposure_pct is not None and total_exposure_pct > max_exp:
        breaches.append("exposure_limit")
    if dd["max_drawdown_pct"] is not None and abs(float(dd["max_drawdown_pct"])) > max_dd:
        breaches.append("max_drawdown_limit")
    if daily_loss_pct is not None and daily_loss_pct < -max_daily:
        breaches.append("daily_loss_limit")
    if len(positions) > max_pos:
        breaches.append("max_positions")

    trades_today = len(trades)  # approximate; timestamps filtered by caller if needed
    if trades_today > max_trades_day:
        breaches.append("max_trades_per_day")

    return {
        "mode": "PAPER_ONLY",
        "classification": {
            "cash": "confirmed_ledger",
            "invested_cost": "confirmed_ledger",
            "market_value": "observed_marks" if missing_marks == 0 else "partial",
            "equity": "approximate_mark_to_market" if equity is not None else "unavailable",
            "realized_pnl": "simulation_fifo",
            "fees_estimated": "simulation_estimate",
            "drawdown": "from_scan_equity_history",
        },
        "initial_capital": float(initial_capital),
        "cash": float(cash),
        "invested_cost": float(invested),
        "positions_market_value": float(mv) if missing_marks == 0 else None,
        "unrealized_pnl": unrealized,
        "realized_pnl": float(pnl_pack["realized_pnl"]),
        "fees_estimated": float(pnl_pack["fees_estimated"]),
        "equity_estimate": float(equity) if equity is not None else None,
        "open_positions": len(positions),
        "missing_marks": missing_marks,
        "exposure_by_asset": exposure,
        "total_exposure_pct_of_initial": total_exposure_pct,
        "drawdown": dd,
        "daily_pnl_pct_vs_first_scan": daily_loss_pct,
        "limits": {
            "max_exposure_pct": max_exp,
            "max_drawdown_pct": max_dd,
            "max_daily_loss_pct": max_daily,
            "max_positions": max_pos,
            "max_trades_per_day": max_trades_day,
            "per_trade_budget": float(limits.get("per_trade_budget", 25)),
        },
        "breaches": breaches,
        "disclaimer": "Métricas de simulación paper. No son resultados reales ni consejo financiero.",
    }
