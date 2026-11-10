"""Backtest largo Etapa W sobre historial Parquet. Sin look-ahead. Sin auto-promoción."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ...active.backtest_b import Book, _fill_buy, _fill_sell, simulate as simulate_ab
from ...demo.indicators import compute_bundle as compute_a
from ...demo.policy import BUY_MIN_FLAGS, BUY_SCORE_MIN, FEE_RATE as A_FEE, SLIP_RATE as A_SLIP
from ..policies_v import FEE_RATE, MAX_EXPOSURE_USDT, MAX_POS_USDT, MAX_POSITIONS, SLIP_RATE
from ..regimes import _ema, classify_regime
from .aggregate import aggregate_bars
from .coverage import aligned_span_ms, summarize_symbol
from .store import load_range


def _rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[-n:]) / n
    al = sum(losses[-n:]) / n
    if al == 0:
        return 100.0
    return 100 - (100 / (1 + ag / al))


def _agg_n(bars: list[dict], n: int) -> list[dict]:
    out: list[dict] = []
    bucket: list[dict] = []
    for c in bars:
        bucket.append(c)
        if len(bucket) == n:
            out.append(
                {
                    "open_time": bucket[0]["open_time"],
                    "open": float(bucket[0]["open"]),
                    "high": max(float(x["high"]) for x in bucket),
                    "low": min(float(x["low"]) for x in bucket),
                    "close": float(bucket[-1]["close"]),
                    "volume": sum(float(x["volume"]) for x in bucket),
                    "is_closed": True,
                }
            )
            bucket = []
    return out


@dataclass
class Aux:
    last_entry: dict[str, int] = field(default_factory=dict)
    regime_pnl: dict[str, list[float]] = field(default_factory=dict)


def _metrics(book: Book, closed: list[float], warm: int, i1: int, data: dict) -> dict[str, Any]:
    marks = {s: float(data[s][i1 - 1]["close"]) for s in data}
    equity = book.mark_equity(marks)
    wins = [x for x in closed if x > 0]
    losses = [x for x in closed if x < 0]
    gw, gl = sum(wins), abs(sum(losses))
    n = len(closed)
    pf = (gw / gl) if gl > 0 else None
    bh0 = sum(float(data[s][warm]["close"]) for s in data) / len(data)
    bh1 = sum(float(data[s][i1 - 1]["close"]) for s in data) / len(data)
    return {
        "equity": round(equity, 4),
        "net_vs_initial": round(equity - 1000.0, 4),
        "buys": book.buys,
        "sells": book.sells,
        "closed_rounds": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n, 6) if n else None,
        "profit_factor": round(pf, 6) if pf is not None else None,
        "expectancy": round(sum(closed) / n, 6) if n else None,
        "max_drawdown_proxy": round(1.0 - (equity / book.peak) if book.peak else 0.0, 6),
        "fees": round(book.fees, 6),
        "slips": round(book.slips, 6),
        "cash_benchmark_net": 0.0,
        "buy_hold_proxy_return": round(bh1 / bh0 - 1.0, 6) if bh0 else None,
        "declare_profitable": False,
        "bars": i1 - warm,
    }


def simulate_on_bars(
    data: dict[str, list[dict]],
    *,
    variant: str,
    i0: int,
    i1: int,
    bar_minutes: int = 5,
) -> dict[str, Any]:
    """Simula sobre barras cerradas (p.ej. 5m). Señal en barra i; fill en close de i (post-cierre)."""
    book = Book()
    aux = Aux()
    closed_pnls: list[float] = []
    warm = max(80, i0)
    fee, slip = FEE_RATE, SLIP_RATE
    # ratios vs 5m
    n15 = max(1, 15 // bar_minutes)
    n60 = max(1, 60 // bar_minutes)

    for i in range(warm, i1):
        marks = {s: float(data[s][i]["close"]) for s in data}
        equity = book.mark_equity(marks)
        book.peak = max(book.peak, equity)
        pause = equity <= book.peak * 0.97
        invested = sum(p.cost for p in book.positions.values())

        for sym in list(book.positions.keys()):
            c = data[sym][: i + 1]
            entry = book.positions[sym].entry
            mark = float(c[-1]["close"])
            action, reason = "HOLD", "hold"
            if variant == "V_TREND":
                c60 = _agg_n(c, n60)
                closes_h = [float(x["close"]) for x in c60[-40:]]
                e20, e50 = _ema(closes_h, 20), _ema(closes_h, 50)
                if mark <= entry * (1 - 0.012):
                    action, reason = "SELL", "sl"
                elif mark >= entry * (1 + 0.024):
                    action, reason = "SELL", "tp"
                elif e20 is not None and e50 is not None and e20 < e50:
                    action, reason = "SELL", "htf_invalidation"
            elif variant == "V_BREAK":
                c15 = _agg_n(c, n15)
                if len(c15) >= 13:
                    window = c15[-13:-1]
                    lo = min(float(x["low"]) for x in window)
                    hi = max(float(x["high"]) for x in window)
                    rng = max(hi - lo, entry * 0.002)
                    sl = max(lo, entry * (1 - 0.02))
                    tp = entry + min(1.5 * rng, entry * 0.03)
                    if mark <= sl:
                        action, reason = "SELL", "sl_range"
                    elif mark >= tp:
                        action, reason = "SELL", "tp_range"
                elif mark <= entry * 0.98:
                    action, reason = "SELL", "sl"
            elif variant == "V_MEAN":
                if mark <= entry * (1 - 0.008):
                    action, reason = "SELL", "sl"
                elif mark >= entry * (1 + 0.012):
                    action, reason = "SELL", "tp"
            else:
                # A-like on last ~120*bar equiv via 5m window
                b5 = c[-80:]
                b1_proxy = c[-120:]
                b = compute_a(b1_proxy, b5)
                if b:
                    if mark <= entry * 0.99:
                        action, reason = "SELL", "stop_loss_1pct"
                    elif mark >= entry * 1.02:
                        action, reason = "SELL", "take_profit_2pct"
                    elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42:
                        action, reason = "SELL", "trend_break"

            if action == "SELL":
                before = book.realized
                reg = classify_regime(c[-120:])["regime"]
                _fill_sell(book, sym, mark, fee, slip)
                delta = book.realized - before
                closed_pnls.append(delta)
                aux.regime_pnl.setdefault(reg, []).append(delta)

        if pause or len(book.positions) >= MAX_POSITIONS or invested >= MAX_EXPOSURE_USDT:
            continue

        for sym in data:
            if sym in book.positions:
                continue
            if aux.last_entry.get(sym, -10**9) > i - 12:
                continue
            c = data[sym][: i + 1]
            allow = False
            reason = "no_signal"
            if variant == "V_TREND":
                c60 = _agg_n(c, n60)
                c15 = _agg_n(c, n15)
                closes_h = [float(x["close"]) for x in c60[-40:]]
                e20, e50 = _ema(closes_h, 20), _ema(closes_h, 50)
                if e20 is None or e50 is None or e20 <= e50 or len(c15) < 25:
                    reason = "no_htf_trend"
                else:
                    closes15 = [float(x["close"]) for x in c15]
                    vols = [float(x["volume"]) for x in c15]
                    e21 = _ema(closes15[-40:], 21)
                    rsi = _rsi(closes15, 14)
                    sma_vol = sum(vols[-20:]) / 20 if len(vols) >= 20 else None
                    close = closes15[-1]
                    if (
                        e21 is not None
                        and rsi is not None
                        and sma_vol is not None
                        and abs(close / e21 - 1.0) <= 0.0035
                        and 40 <= rsi <= 55
                        and vols[-1] >= sma_vol
                    ):
                        allow = True
                        reason = "v_trend_entry"
            elif variant == "V_BREAK":
                c15 = _agg_n(c, n15)
                if len(c15) >= 13:
                    window = c15[-13:-1]
                    hi = max(float(x["high"]) for x in window)
                    vols = [float(x["volume"]) for x in c15]
                    sma_vol = sum(vols[-20:]) / 20 if len(vols) >= 20 else 0
                    close = float(c15[-1]["close"])
                    vol = float(c15[-1]["volume"])
                    atr_pct = (hi - min(float(x["low"]) for x in window)) / close if close else 0
                    if close > hi and vol > 1.2 * sma_vol and atr_pct >= 1.2 * (fee + slip):
                        allow = True
                        reason = "v_break_entry"
            elif variant == "V_MEAN":
                reg = classify_regime(c[-120:])["regime"]
                if "sideways" in reg:
                    closes = [float(x["close"]) for x in c]
                    rsi = _rsi(closes, 14)
                    e21 = _ema(closes[-40:], 21)
                    close = closes[-1]
                    if rsi is not None and e21 is not None and rsi < 30 and close < e21 * 0.995:
                        allow = True
                        reason = "v_mean_entry"
            elif variant == "A_BASELINE":
                b = compute_a(c[-120:], c[-80:])
                if b and int(b["flags_true"]) >= BUY_MIN_FLAGS and float(b["signal_score"]) >= BUY_SCORE_MIN:
                    allow = True
                    reason = "demo_buy"
                    fee, slip = A_FEE, A_SLIP

            book.reasons[reason] = book.reasons.get(reason, 0) + 1
            if allow:
                book.signals_buy += 1
                if _fill_buy(book, sym, float(c[-1]["close"]), fee, slip, MAX_POS_USDT):
                    aux.last_entry[sym] = i

    m = _metrics(book, closed_pnls, warm, i1, data)
    m["variant"] = variant
    m["regime_pnl"] = {
        k: {"n": len(v), "sum": round(sum(v), 6), "avg": round(sum(v) / len(v), 6) if v else None}
        for k, v in aux.regime_pnl.items()
    }
    m["bar_minutes"] = bar_minutes
    return m


def load_multi_symbol_bars(symbols: list[str], interval: str = "15m") -> dict[str, list[dict]] | None:
    """Carga TF agregado (15m por defecto) para backtest largo viable en CPU."""
    span = aligned_span_ms(symbols, interval) or aligned_span_ms(symbols, "1m")
    if not span:
        return None
    start, end = span
    data: dict[str, list[dict]] = {}
    for s in symbols:
        rows = load_range(s, interval, start, end)
        if len(rows) < 500:
            rows1 = load_range(s, "1m", start, end)
            rows = aggregate_bars(rows1, interval)
        data[s] = rows
    n = min(len(v) for v in data.values())
    if n < 500:
        return None
    return {s: v[-n:] for s, v in data.items()}


def run_etapa_w(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    coverage = {s: summarize_symbol(s, "1m") for s in symbols}
    # 1h: ~8.7k barras/año — viable en CPU; señales en vela cerrada; fill en close.
    # 1m/15m Parquet permanece para auditoría; no look-ahead.
    bar_minutes = 60
    data = load_multi_symbol_bars(symbols, "1h")
    if not data:
        return {
            "available": False,
            "paper_only": True,
            "reason": "historial_insuficiente",
            "coverage": coverage,
            "claim": {"declare_winner": False, "declare_profitable": False},
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    n = min(len(v) for v in data.values())
    # 70% IS, 20% OOS, 10% HOLDOUT (nunca para decidir)
    is_end = int(n * 0.70)
    oos_end = int(n * 0.90)
    hold_end = n
    variants = ["A_BASELINE", "V_TREND", "V_BREAK", "V_MEAN"]
    is_res = {
        v: simulate_on_bars(data, variant=v, i0=80, i1=is_end, bar_minutes=bar_minutes)
        for v in variants
    }
    oos_res = {
        v: simulate_on_bars(data, variant=v, i0=is_end, i1=oos_end, bar_minutes=bar_minutes)
        for v in variants
    }
    # Holdout computed for reporting only — not used to tune
    hold_res = {
        v: simulate_on_bars(data, variant=v, i0=oos_end, i1=hold_end, bar_minutes=bar_minutes)
        for v in variants
    }

    b_full = None
    try:
        # B on same 5m window descriptive
        b_full = simulate_ab(data, mode="B")
    except Exception as exc:
        b_full = {"error": type(exc).__name__, "detail": str(exc)[:120]}

    approval = []
    for vid, r in oos_res.items():
        if vid == "A_BASELINE":
            continue
        reasons = []
        ok = True
        if (r.get("closed_rounds") or 0) < 30:
            ok = False
            reasons.append("pocas_operaciones_oos")
        if (r.get("net_vs_initial") or 0) <= 0:
            ok = False
            reasons.append("neto_oos_no_positivo")
        if r.get("profit_factor") is not None and r["profit_factor"] < 1.0:
            ok = False
            reasons.append("profit_factor_oos_<1")
        # holdout must not be used for promotion; if inspected and negative, note
        h = hold_res.get(vid) or {}
        if (h.get("net_vs_initial") or 0) <= 0:
            reasons.append("holdout_neto_no_positivo_informativo")
        approval.append(
            {
                "id": vid,
                "promote_to_paper_trial": False,
                "passes_research_filters": False,  # never auto
                "filter_notes": reasons or ["filtros_ok_pero_sin_autorizacion"],
                "status": "rejected" if not ok else "research_only_needs_auth",
            }
        )

    first_t = int(data[symbols[0]][0]["open_time"])
    last_t = int(data[symbols[0]][-1]["open_time"])
    return {
        "available": True,
        "paper_only": True,
        "etapa": "W",
        "symbols": symbols,
        "bar_interval": "1h",
        "bars_per_symbol": n,
        "note": (
            "Simulación sobre 1h agregados desde 1m Vision (velas cerradas). "
            "1m/5m/15m Parquet quedan para auditoría; sin look-ahead."
        ),
        "span": {
            "first_open_time": first_t,
            "last_open_time": last_t,
            "first_iso": datetime.fromtimestamp(first_t / 1000, tz=timezone.utc).isoformat(),
            "last_iso": datetime.fromtimestamp(last_t / 1000, tz=timezone.utc).isoformat(),
        },
        "coverage": coverage,
        "walk_forward": {
            "is_end": is_end,
            "oos_end": oos_end,
            "holdout_end": hold_end,
            "note": "Holdout final ~10% no se usa para ajustar parámetros ni promoción.",
        },
        "in_sample": is_res,
        "out_of_sample": oos_res,
        "holdout": hold_res,
        "b_baseline_full_window": b_full,
        "approval_gate": approval,
        "claim": {
            "declare_winner": False,
            "declare_profitable": False,
            "reason": (
                "Ninguna variante se declara rentable solo por ampliar historial. "
                "Sin autorización explícita no hay prueba prospectiva."
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = p.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(json.dumps(run_etapa_w(symbols), indent=2, default=str))


if __name__ == "__main__":
    main()
