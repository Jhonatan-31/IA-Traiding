"""Financial metric helpers with explicit units and dependence-aware CIs."""
from __future__ import annotations

from typing import Any

import numpy as np


METRIC_UNITS = {
    "per_trade_fraction": (
        "Fractional PnL of one round-trip after costs: (sell/buy)-1. "
        "Not portfolio equity change."
    ),
    "sum_per_trade_fractions": (
        "Sum of per-trade fractions. Overlapping trades are added independently; "
        "NOT equal to compounded portfolio return."
    ),
    "portfolio_equity_fraction": (
        "Change in account equity / initial_capital over the backtest window."
    ),
    "drawdown_equity_fraction": (
        "Peak-to-trough decline of mark-to-market equity curve (fraction of peak)."
    ),
}


def profit_factor(pnls: np.ndarray | list[float]) -> float | None:
    arr = np.asarray(pnls, dtype=float)
    gains = float(arr[arr > 0].sum()) if np.any(arr > 0) else 0.0
    losses = float((-arr[arr < 0]).sum()) if np.any(arr < 0) else 0.0
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return gains / losses


def max_drawdown_from_equity(equity: np.ndarray | list[float]) -> float | None:
    """Return max drawdown as negative fraction of peak (e.g. -0.12 = -12%)."""
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return None
    peak = np.maximum.accumulate(eq)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, eq / peak - 1.0, 0.0)
    return float(dd.min()) if len(dd) else None


def max_drawdown_from_pnl_sum(pnls: np.ndarray | list[float]) -> float | None:
    """Legacy Etapa-F style DD on cumulative sum of trade fractions."""
    arr = np.asarray(pnls, dtype=float)
    if len(arr) == 0:
        return None
    curve = np.cumsum(arr)
    # treat as equity starting at 0 — DD measured in absolute fraction-sum units
    peak = np.maximum.accumulate(curve)
    dd = curve - peak
    return float(dd.min())


def block_bootstrap_ci(
    values: list[float],
    *,
    block_size: int = 20,
    n_boot: int = 400,
    alpha: float = 0.05,
    seed: int = 7,
) -> dict[str, Any]:
    """
    Moving-block bootstrap for temporally dependent returns.
    Still approximate when cross-sectional correlation exists across assets.
    """
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    if n < 2:
        return {
            "mean": float(arr.mean()) if n else None,
            "low": None,
            "high": None,
            "n": n,
            "method": "block_bootstrap",
            "block_size": block_size,
            "warning": "insufficient_n",
        }
    bs = max(1, min(block_size, n))
    rng = np.random.default_rng(seed)
    means = []
    n_blocks = int(np.ceil(n / bs))
    for _ in range(n_boot):
        sample = []
        for _b in range(n_blocks):
            start = int(rng.integers(0, max(n - bs + 1, 1)))
            sample.extend(arr[start : start + bs])
        sample = sample[:n]
        means.append(float(np.mean(sample)))
    return {
        "mean": float(arr.mean()),
        "low": float(np.quantile(means, alpha / 2)),
        "high": float(np.quantile(means, 1 - alpha / 2)),
        "n": n,
        "method": "block_bootstrap",
        "block_size": bs,
        "warning": (
            "Cross-asset correlation not fully removed; treat as approximate."
        ),
    }


def paired_strategy_diff(
    a: list[float], b: list[float]
) -> dict[str, Any]:
    """Paired difference a-b on aligned trade/period returns."""
    n = min(len(a), len(b))
    if n == 0:
        return {"n": 0, "mean_diff": None, "ci": None}
    diff = [float(a[i]) - float(b[i]) for i in range(n)]
    return {
        "n": n,
        "mean_diff": float(np.mean(diff)),
        "ci": block_bootstrap_ci(diff, block_size=max(5, n // 10)),
        "unit": "per_trade_fraction_difference",
    }


def multiple_testing_warning(n_strategies: int) -> str:
    return (
        f"Se evaluaron {n_strategies} estrategias. Sin corrección formal, "
        "la probabilidad de un falso positivo aumenta. No declarar edge "
        "salvo evidencia pre-registrada y holdout intacto."
    )
