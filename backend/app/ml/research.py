"""Etapa G research runner — strategies + portfolio backtest + validation. Offline only."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dataset import load_jsonl, quality_report
from .expected_return import empirical_gain_loss_from_history, estimate_expected_net
from .labels import HORIZON, net_forward_return
from .market_features import summarize_listing_bias
from .metrics_audit import METRIC_UNITS, multiple_testing_warning
from .portfolio_backtest import run_portfolio_backtest
from .strategies import (
    SPECS,
    list_strategy_specs,
    signal_breakout_liquidity,
    signal_mean_reversion,
    signal_momentum_vol,
    signal_sma10_50,
    signal_trend_volume,
)
from .train import build_xy


def _group(rows: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = {}
    for r in rows:
        g.setdefault(r["symbol"], []).append(r)
    for s in g:
        g[s] = sorted(g[s], key=lambda x: x["open_time"])
    return g


def _signals_for(name: str, candles: list[dict]) -> list[int]:
    closes = [float(c["close"]) for c in candles]
    if name == "cash":
        return [0] * len(candles)
    if name == "buy_hold":
        return [1] * len(candles)
    if name == "sma10_50":
        return signal_sma10_50(closes)
    if name == "momentum_vol_filter":
        return signal_momentum_vol(candles)
    if name == "mean_reversion":
        return signal_mean_reversion(candles)
    if name == "trend_volume":
        return signal_trend_volume(candles)
    if name == "breakout_liquidity":
        return signal_breakout_liquidity(candles)
    return [0] * len(candles)


def _slice_groups(
    groups: dict[str, list[dict]], t0: int, t1: int
) -> dict[str, list[dict]]:
    out = {}
    for sym, rows in groups.items():
        sl = [r for r in rows if t0 <= int(r["open_time"]) <= t1]
        if len(sl) >= 60:
            out[sym] = sl
    return out


def _run_named(
    groups: dict[str, list[dict]], name: str, initial_capital: float
) -> dict[str, Any]:
    spec = SPECS[name]
    signals = {sym: _signals_for(name, rows) for sym, rows in groups.items()}
    r = run_portfolio_backtest(
        bars_by_symbol=groups,
        signals_by_symbol=signals,
        initial_capital=initial_capital,
        horizon=spec.horizon_bars,
        max_positions=spec.max_positions,
        max_exposure_pct=float(spec.risk_limits.get("max_exposure_pct", 50)),
        fee_rate=spec.fee_rate,
        slip_rate=spec.slip_rate,
    )
    r["strategy"] = name
    r["spec"] = {
        "entry": spec.entry,
        "exit": spec.exit,
        "abstain_when": spec.abstain_when,
        "auto_activate": False,
    }
    return r


def _public(r: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in r.items() if k != "closed_pnls"}


def run_research(
    dataset_path: Path,
    artifact_dir: Path,
    *,
    initial_capital: float = 1000.0,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    rows = load_jsonl(dataset_path)
    groups = _group(rows)
    quality = quality_report(rows, rows[0]["interval"] if rows else "1h")
    listing = summarize_listing_bias(quality.get("symbols") or {})

    strategy_names = [
        "cash",
        "buy_hold",
        "sma10_50",
        "momentum_vol_filter",
        "mean_reversion",
        "trend_volume",
        "breakout_liquidity",
    ]

    times = sorted({int(r["open_time"]) for r in rows})
    cut = times[int(len(times) * 0.7)]
    embargo_ms = HORIZON * 3_600_000
    holdout_start = cut + embargo_ms
    select_groups = _slice_groups(groups, times[0], cut)
    holdout_groups = _slice_groups(groups, holdout_start, times[-1])

    selection = [_run_named(select_groups, n, initial_capital) for n in strategy_names]
    ranked = sorted(
        selection,
        key=lambda x: (
            x.get("total_return_fraction") is not None,
            x.get("total_return_fraction") if x.get("total_return_fraction") is not None else -999,
        ),
        reverse=True,
    )
    best = ranked[0]["strategy"] if ranked else "cash"

    holdout = [_run_named(holdout_groups, n, initial_capital) for n in strategy_names]

    cost_sens: dict[str, list] = {}
    for name in ("sma10_50", "momentum_vol_filter", "mean_reversion"):
        cost_sens[name] = []
        for fee, slip in ((0.0005, 0.0005), (0.001, 0.001), (0.002, 0.002)):
            spec = SPECS[name]
            signals = {
                sym: _signals_for(name, rows) for sym, rows in select_groups.items()
            }
            r = run_portfolio_backtest(
                bars_by_symbol=select_groups,
                signals_by_symbol=signals,
                initial_capital=initial_capital,
                horizon=spec.horizon_bars,
                max_positions=spec.max_positions,
                max_exposure_pct=float(spec.risk_limits.get("max_exposure_pct", 50)),
                fee_rate=fee,
                slip_rate=slip,
            )
            cost_sens[name].append(
                {
                    "fee_rate": fee,
                    "slip_rate": slip,
                    "total_return_fraction": r["total_return_fraction"],
                    "max_drawdown_equity": r["max_drawdown_equity"],
                    "n_closed": r["n_closed"],
                }
            )

    _, y, meta = build_xy(rows)
    nets = []
    for m, _lab in zip(meta, y):
        candles = groups[m["symbol"]]
        i = m["index"]
        j = i + HORIZON
        if j < len(candles):
            nets.append(
                net_forward_return(
                    float(candles[i]["close"]), float(candles[j]["close"])
                )
            )
    gl = empirical_gain_loss_from_history(nets)
    e_example = estimate_expected_net(
        p_up=0.55,
        mean_gain_if_up=gl.get("mean_gain_if_up"),
        mean_loss_if_down=gl.get("mean_loss_if_down"),
        fee_rate=0.0,
        slip_rate=0.0,
    )

    def _robust(h: dict) -> bool:
        tr = h.get("total_return_fraction")
        ci = h.get("block_ci_trade_fractions") or {}
        return bool(tr is not None and tr > 0 and ci.get("low") is not None and ci["low"] > 0)

    robust_any = any(_robust(h) for h in holdout if h["strategy"] != "cash")

    report: dict[str, Any] = {
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metric_units": METRIC_UNITS,
        "dataset": {
            "path": str(dataset_path),
            "rows": len(rows),
            "symbols": len(groups),
            "quality_totals": quality.get("totals"),
            "listing_bias": listing,
        },
        "execution_model": "signal_close_t__fill_open_t_plus_1",
        "selection_window": {
            "to_open_ms": cut,
            "results": [_public(r) for r in selection],
            "best_by_total_return": best,
        },
        "final_holdout": {
            "from_open_ms": holdout_start,
            "embargo_ms": embargo_ms,
            "results": [_public(h) for h in holdout],
            "preselected_strategy": best,
            "preselected_holdout": _public(
                next(h for h in holdout if h["strategy"] == best)
            ),
        },
        "cost_sensitivity": cost_sens,
        "expected_return_example": {"empirical_gain_loss": gl, "at_p_0_55": e_example},
        "shadow_replay_caveat": {
            "mean_net_return_is_not_strategy_pnl": True,
            "explanation": (
                "Shadow replay averages hypothetical long nets including HOLD rows. "
                "It is not executable portfolio PnL."
            ),
        },
        "strategy_specs": list_strategy_specs(),
        "multiple_testing": multiple_testing_warning(len(strategy_names)),
        "robust_edge_any": robust_any,
        "paper_ai_authorized": False,
        "auto_activate": False,
        "conclusion": (
            "Al menos una estrategia muestra señales de edge en holdout; requiere revisión humana."
            if robust_any
            else (
                "Ninguna estrategia demuestra edge económico robusto en holdout bajo "
                "ejecución t+1 y costos explícitos. Se mantiene Shadow AI; PAPER_AI no autorizado."
            )
        ),
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = artifact_dir / f"research_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (artifact_dir / "last_research.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    report["artifact_path"] = str(out_path)
    return report
