"""
Portfolio historical simulator with next-bar execution.

Signal on closed bar t (using only data <= t).
Order submitted for bar t+1 open (modeled as open price with slip+fee).
Exit after horizon bars from entry bar, at that bar's open (+costs), unless specified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .metrics_audit import max_drawdown_from_equity, profit_factor


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_cost_cash: float
    entry_open_ms: int
    exit_index: int
    bars_held: int = 0


@dataclass
class PortfolioState:
    cash: float
    equity_curve: list[float] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    closed_pnls: list[float] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    fills: list[dict] = field(default_factory=list)


def _mark_equity(cash: float, positions: list[Position], marks: dict[str, float]) -> float:
    eq = cash
    for p in positions:
        px = marks.get(p.symbol)
        if px is None:
            eq += p.entry_cost_cash  # stale: keep cost basis
        else:
            eq += p.qty * px
    return eq


def run_portfolio_backtest(
    *,
    bars_by_symbol: dict[str, list[dict]],
    signals_by_symbol: dict[str, list[int]],
    initial_capital: float = 1000.0,
    horizon: int = 6,
    max_positions: int = 5,
    max_exposure_pct: float = 50.0,
    risk_per_trade_pct: float = 5.0,
    fee_rate: float = 0.001,
    slip_rate: float = 0.001,
    min_quote_volume: float | None = None,
) -> dict[str, Any]:
    """
    Event-driven over union of timestamps. Execution at next bar open after signal.
    """
    # Build timeline of open_times
    all_times = sorted({int(b["open_time"]) for rows in bars_by_symbol.values() for b in rows})
    index_of = {
        sym: {int(b["open_time"]): i for i, b in enumerate(rows)}
        for sym, rows in bars_by_symbol.items()
    }
    state = PortfolioState(cash=initial_capital)
    pending_entries: list[dict] = []  # execute next time we see symbol's next bar

    for t_i, t in enumerate(all_times):
        marks: dict[str, float] = {}
        for sym, rows in bars_by_symbol.items():
            idx = index_of[sym].get(t)
            if idx is not None:
                marks[sym] = float(rows[idx]["close"])

        # 1) Process exits due at this open
        still: list[Position] = []
        for pos in state.positions:
            rows = bars_by_symbol[pos.symbol]
            idx = index_of[pos.symbol].get(t)
            if idx is None:
                still.append(pos)
                continue
            if idx >= pos.exit_index:
                open_px = float(rows[idx]["open"])
                sell = open_px * (1 - slip_rate) * (1 - fee_rate)
                proceeds = pos.qty * sell
                state.cash += proceeds
                pnl_frac = proceeds / pos.entry_cost_cash - 1.0
                state.closed_pnls.append(pnl_frac)
                state.fills.append(
                    {
                        "side": "SELL",
                        "symbol": pos.symbol,
                        "price": sell,
                        "t": t,
                        "pnl_frac": pnl_frac,
                    }
                )
            else:
                still.append(pos)
        state.positions = still

        # 2) Execute pending entries at this bar open
        still_pending = []
        for order in pending_entries:
            sym = order["symbol"]
            rows = bars_by_symbol[sym]
            idx = index_of[sym].get(t)
            if idx is None:
                still_pending.append(order)
                continue
            if idx != order["exec_index"]:
                # skipped gap → reject
                state.rejected.append({**order, "reason": "exec_bar_gap"})
                continue
            open_px = float(rows[idx]["open"])
            if min_quote_volume is not None:
                # volume*open as crude quote volume proxy for the bar
                qv = float(rows[idx]["volume"]) * open_px
                if qv < min_quote_volume:
                    state.rejected.append({**order, "reason": "liquidity"})
                    continue
            if len(state.positions) >= max_positions:
                state.rejected.append({**order, "reason": "max_positions"})
                continue
            invested = sum(p.entry_cost_cash for p in state.positions)
            exposure_pct = (invested / (state.cash + invested) * 100) if (state.cash + invested) else 0
            if exposure_pct >= max_exposure_pct:
                state.rejected.append({**order, "reason": "max_exposure"})
                continue
            budget = min(
                state.cash * (risk_per_trade_pct / 100.0),
                state.cash * 0.95,
            )
            if budget < 10:
                state.rejected.append({**order, "reason": "insufficient_cash"})
                continue
            buy = open_px * (1 + slip_rate) * (1 + fee_rate)
            qty = budget / buy
            state.cash -= budget
            exit_index = idx + horizon
            state.positions.append(
                Position(
                    symbol=sym,
                    qty=qty,
                    entry_price=buy,
                    entry_cost_cash=budget,
                    entry_open_ms=t,
                    exit_index=exit_index,
                )
            )
            state.fills.append(
                {"side": "BUY", "symbol": sym, "price": buy, "t": t, "budget": budget}
            )
        pending_entries = still_pending

        # 3) New signals on closed bar t → schedule for next bar of that symbol
        for sym, rows in bars_by_symbol.items():
            idx = index_of[sym].get(t)
            if idx is None:
                continue
            sigs = signals_by_symbol.get(sym) or []
            if idx >= len(sigs) or sigs[idx] != 1:
                continue
            # already in position?
            if any(p.symbol == sym for p in state.positions):
                continue
            # need next bar
            if idx + 1 >= len(rows):
                state.rejected.append(
                    {"symbol": sym, "t": t, "reason": "no_next_bar_for_execution"}
                )
                continue
            pending_entries.append(
                {
                    "symbol": sym,
                    "signal_index": idx,
                    "exec_index": idx + 1,
                    "signal_t": t,
                }
            )

        eq = _mark_equity(state.cash, state.positions, marks)
        state.equity_curve.append(eq)

    # Force close remaining at last available close (conservative mark, with costs)
    for pos in list(state.positions):
        rows = bars_by_symbol[pos.symbol]
        last = rows[-1]
        px = float(last["close"]) * (1 - slip_rate) * (1 - fee_rate)
        proceeds = pos.qty * px
        state.cash += proceeds
        state.closed_pnls.append(proceeds / pos.entry_cost_cash - 1.0)
    state.positions = []
    final_eq = state.cash
    if state.equity_curve:
        state.equity_curve.append(final_eq)

    init = initial_capital
    total_ret = (final_eq / init - 1.0) if init else None
    from .metrics_audit import block_bootstrap_ci

    return {
        "initial_capital": init,
        "final_equity": final_eq,
        "total_return_fraction": total_ret,
        "unit": "portfolio_equity_fraction",
        "max_drawdown_equity": max_drawdown_from_equity(state.equity_curve),
        "n_fills": len(state.fills),
        "n_closed": len(state.closed_pnls),
        "n_rejected": len(state.rejected),
        "reject_reasons": _count_reasons(state.rejected),
        "avg_trade_fraction": float(sum(state.closed_pnls) / len(state.closed_pnls))
        if state.closed_pnls
        else None,
        "profit_factor_trades": profit_factor(state.closed_pnls),
        "sum_trade_fractions": float(sum(state.closed_pnls)) if state.closed_pnls else 0.0,
        "closed_pnls": list(state.closed_pnls),
        "block_ci_trade_fractions": block_bootstrap_ci(state.closed_pnls)
        if state.closed_pnls
        else None,
        "execution_model": "signal_close_t__fill_open_t_plus_1",
        "costs": {"fee_rate": fee_rate, "slip_rate": slip_rate},
        "equity_points": len(state.equity_curve),
    }


def _count_reasons(rejected: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rejected:
        k = str(r.get("reason"))
        out[k] = out.get(k, 0) + 1
    return out
