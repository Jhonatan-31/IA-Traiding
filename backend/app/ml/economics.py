"""Economic metrics under consistent execution assumptions."""
from __future__ import annotations

from typing import Any

import numpy as np

from .calibration import bootstrap_ci
from .labels import net_forward_return


def trade_stats(pnls: list[float]) -> dict[str, Any]:
    if not pnls:
        return {
            "trades": 0,
            "net_return_sum": 0.0,
            "avg_trade": None,
            "win_rate": None,
            "expectancy": None,
            "max_drawdown": None,
            "profit_factor": None,
            "sharpe_approx": None,
            "unit": "sum_per_trade_fractions",
            "warning": (
                "net_return_sum is Σ(per-trade fractions), not portfolio equity return. "
                "IID bootstrap CI overstates precision under dependence."
            ),
            "costs_note": "roundtrip fee+slip embedded in net_forward_return",
        }
    arr = np.asarray(pnls, dtype=float)
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) else None
    gains = float(arr[arr > 0].sum()) if np.any(arr > 0) else 0.0
    losses = float(-arr[arr < 0].sum()) if np.any(arr < 0) else 0.0
    pf = (gains / losses) if losses > 0 else None
    wins = float((arr > 0).mean())
    # Sharpe on trade returns (not annualized) — only if variance > 0
    sharpe = None
    if arr.std(ddof=1) > 1e-12:
        sharpe = float(arr.mean() / arr.std(ddof=1) * np.sqrt(len(arr)))
    return {
        "trades": int(len(arr)),
        "net_return_sum": float(arr.sum()),
        "avg_trade": float(arr.mean()),
        "win_rate": wins,
        "expectancy": float(arr.mean()),
        "max_drawdown": max_dd,
        "profit_factor": float(pf) if pf is not None else None,
        "sharpe_approx": sharpe,
        "net_return_ci": bootstrap_ci(list(arr)),
        "unit": "sum_per_trade_fractions",
        "warning": (
            "net_return_sum is Σ(per-trade fractions), not portfolio equity return. "
            "IID bootstrap CI overstates precision under dependence."
        ),
        "costs_note": "roundtrip fee+slip embedded in net_forward_return",
    }


def policy_pnls(
    meta_slice: list[dict],
    rows_by_sym: dict[str, list[dict]],
    take_mask: np.ndarray,
    horizon: int,
) -> list[float]:
    pnls: list[float] = []
    for keep, m in zip(take_mask, meta_slice):
        if not keep:
            continue
        candles = rows_by_sym[m["symbol"]]
        i = m["index"]
        j = i + horizon
        if j >= len(candles):
            continue
        pnls.append(
            net_forward_return(float(candles[i]["close"]), float(candles[j]["close"]))
        )
    return pnls


def aggregate_strategy_table(fold_reports: list[dict]) -> list[dict[str, Any]]:
    """Average net metrics across folds for comparable strategies."""
    keys = [
        ("cash", "policy_cash"),
        ("buy_hold", "policy_always_long"),
        ("sma10_50", "policy_sma"),
        ("logistic", "policy_logistic"),
        ("hist_gb", "policy_hist_gb"),
        ("hist_gb_calibrated", "policy_hist_gb_calibrated"),
    ]
    rows = []
    for name, key in keys:
        nets = []
        trades = []
        dds = []
        pfs = []
        for fr in fold_reports:
            pol = fr.get(key) or {}
            if "net_return_sum" in pol:
                nets.append(float(pol["net_return_sum"]))
            if pol.get("trades") is not None:
                trades.append(int(pol["trades"]))
            if pol.get("max_drawdown") is not None:
                dds.append(float(pol["max_drawdown"]))
            if pol.get("profit_factor") is not None:
                pfs.append(float(pol["profit_factor"]))
        rows.append(
            {
                "strategy": name,
                "folds": len(fold_reports),
                "mean_net_return_sum": float(np.mean(nets)) if nets else None,
                "net_return_ci": bootstrap_ci(nets) if nets else None,
                "mean_trades": float(np.mean(trades)) if trades else None,
                "mean_max_drawdown": float(np.mean(dds)) if dds else None,
                "mean_profit_factor": float(np.mean(pfs)) if pfs else None,
                "robust_edge": False,  # filled by caller if evidence warrants
            }
        )
    return rows


def sensitivity_to_costs(
    meta_slice: list[dict],
    rows_by_sym: dict[str, list[dict]],
    take_mask: np.ndarray,
    horizon: int,
    fee_slip_pairs: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Recompute net with alternate fee/slip (does not mutate global TARGET)."""
    out = []
    for fee, slip in fee_slip_pairs:
        pnls = []
        for keep, m in zip(take_mask, meta_slice):
            if not keep:
                continue
            candles = rows_by_sym[m["symbol"]]
            i = m["index"]
            j = i + horizon
            if j >= len(candles):
                continue
            entry = float(candles[i]["close"])
            exit_px = float(candles[j]["close"])
            buy = entry * (1 + slip) * (1 + fee)
            sell = exit_px * (1 - slip) * (1 - fee)
            pnls.append(sell / buy - 1.0)
        out.append(
            {
                "fee_rate": fee,
                "slip_rate": slip,
                "roundtrip_approx": 2 * (fee + slip),
                **trade_stats(pnls),
            }
        )
    return out
