"""Etapa X — diagnóstico condicional por régimen / calidad de señales.

Usa historial Parquet 12m (no REST). Holdout W declarado CONSUMIDO.
Unidades: net_pnl y expectancy en USDT sobre capital inicial 1000 USDT
(no son porcentajes salvo campos *_pct / buy_hold_proxy_return).
"""
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ...active.backtest_b import Book, _fill_buy, _fill_sell
from ...demo.indicators import compute_bundle as compute_a
from ...demo.policy import BUY_MIN_FLAGS, BUY_SCORE_MIN, FEE_RATE as A_FEE, SLIP_RATE as A_SLIP
from ..policies_v import FEE_RATE, MAX_EXPOSURE_USDT, MAX_POS_USDT, MAX_POSITIONS, SLIP_RATE
from ..regimes import _ema
from .backtest_w import _agg_n, _rsi, load_multi_symbol_bars
from .coverage import summarize_symbol
from .regimes_x import classify_regime_x, regime_histogram

MIN_SEGMENT_N = 30  # no concluir con menos operaciones
HOLDOUT_W_CONSUMED = True  # Etapa W ya inspeccionó el 10% final
FEE = FEE_RATE
SLIP = SLIP_RATE

# Hipótesis fijadas ANTES de mirar segmentos (Etapa X)
HYPOTHESES = [
    {
        "id": "H1",
        "text": "A_BASELINE concentra pérdidas en sideways|low_volatility",
        "variant": "A_BASELINE",
        "regime_tv": "sideways|low_volatility",
        "expect": "worse_than_overall",
    },
    {
        "id": "H2",
        "text": "V-BREAK tiene expectancy neta >0 en uptrend|high_volatility con N≥30",
        "variant": "V_BREAK",
        "regime_tv": "uptrend|high_volatility",
        "expect": "positive_expectancy",
    },
    {
        "id": "H3",
        "text": "V-TREND opera y gana en uptrend|normal_volatility o high_volatility",
        "variant": "V_TREND",
        "regime_tv_prefix": "uptrend|",
        "expect": "positive_expectancy",
    },
    {
        "id": "H4",
        "text": "V-MEAN tiene edge en sideways|low_volatility",
        "variant": "V_MEAN",
        "regime_tv": "sideways|low_volatility",
        "expect": "positive_expectancy",
    },
]


@dataclass
class OpenPos:
    symbol: str
    entry_i: int
    entry_px: float
    qty: float
    fee_entry: float
    slip_entry: float
    regime_tv: str
    volume: str
    hour_utc: int | None
    reason: str
    mfe: float = 0.0  # max favorable excursion (frac)
    mae: float = 0.0  # max adverse (frac, positive number)


@dataclass
class AuxX:
    last_entry: dict[str, int] = field(default_factory=dict)
    opens: dict[str, OpenPos] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)


def _units_note() -> dict[str, str]:
    return {
        "net_pnl": "USDT absolutos (capital inicial simulado = 1000 USDT)",
        "expectancy": "USDT medios por operación cerrada (neto de fee+slip en fills)",
        "net_vs_initial": "equity_final - 1000 (USDT)",
        "buy_hold_proxy_return": "fracción (p.ej. -0.07 = −7%)",
        "max_drawdown_proxy": "fracción del pico (0.01 = 1%)",
        "mfe_mae": "fracción respecto al precio de entrada (diagnóstico post-entrada)",
        "source": "Parquet Vision 1h agregado desde 1m; no endpoint REST limit=1000",
    }


def _entry_signal(
    variant: str,
    c: list[dict],
    *,
    bar_minutes: int,
) -> tuple[bool, str, float, float]:
    fee, slip = FEE, SLIP
    n15 = max(1, 15 // bar_minutes)
    n60 = max(1, 60 // bar_minutes)
    allow = False
    reason = "no_signal"
    if variant == "V_TREND":
        c60 = _agg_n(c, n60) if n60 > 1 else c
        c15 = _agg_n(c, n15) if n15 > 1 else c
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
                allow, reason = True, "v_trend_entry"
    elif variant == "V_BREAK":
        c15 = _agg_n(c, n15) if n15 > 1 else c
        if len(c15) >= 13:
            window = c15[-13:-1]
            hi = max(float(x["high"]) for x in window)
            vols = [float(x["volume"]) for x in c15]
            sma_vol = sum(vols[-20:]) / 20 if len(vols) >= 20 else 0
            close = float(c15[-1]["close"])
            vol = float(c15[-1]["volume"])
            atr_pct = (hi - min(float(x["low"]) for x in window)) / close if close else 0
            if close > hi and vol > 1.2 * sma_vol and atr_pct >= 1.2 * (fee + slip):
                allow, reason = True, "v_break_entry"
    elif variant == "V_MEAN":
        reg = classify_regime_x(c)["regime_tv"]
        if "sideways" in reg:
            closes = [float(x["close"]) for x in c]
            rsi = _rsi(closes, 14)
            e21 = _ema(closes[-40:], 21)
            close = closes[-1]
            if rsi is not None and e21 is not None and rsi < 30 and close < e21 * 0.995:
                allow, reason = True, "v_mean_entry"
    elif variant == "A_BASELINE":
        b = compute_a(c[-120:], c[-80:])
        if b and int(b["flags_true"]) >= BUY_MIN_FLAGS and float(b["signal_score"]) >= BUY_SCORE_MIN:
            allow, reason = True, "demo_buy"
            fee, slip = A_FEE, A_SLIP
    return allow, reason, fee, slip


def _exit_signal(
    variant: str,
    c: list[dict],
    entry: float,
    mark: float,
    *,
    bar_minutes: int,
) -> tuple[str, str]:
    n15 = max(1, 15 // bar_minutes)
    n60 = max(1, 60 // bar_minutes)
    action, reason = "HOLD", "hold"
    if variant == "V_TREND":
        c60 = _agg_n(c, n60) if n60 > 1 else c
        closes_h = [float(x["close"]) for x in c60[-40:]]
        e20, e50 = _ema(closes_h, 20), _ema(closes_h, 50)
        if mark <= entry * (1 - 0.012):
            action, reason = "SELL", "sl"
        elif mark >= entry * (1 + 0.024):
            action, reason = "SELL", "tp"
        elif e20 is not None and e50 is not None and e20 < e50:
            action, reason = "SELL", "htf_invalidation"
    elif variant == "V_BREAK":
        c15 = _agg_n(c, n15) if n15 > 1 else c
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
        b = compute_a(c[-120:], c[-80:])
        if b:
            if mark <= entry * 0.99:
                action, reason = "SELL", "stop_loss_1pct"
            elif mark >= entry * 1.02:
                action, reason = "SELL", "take_profit_2pct"
            elif b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42:
                action, reason = "SELL", "trend_break"
    return action, reason


def simulate_trades(
    data: dict[str, list[dict]],
    *,
    variant: str,
    i0: int,
    i1: int,
    bar_minutes: int = 60,
) -> dict[str, Any]:
    book = Book()
    aux = AuxX()
    warm = max(80, i0)
    fee_def, slip_def = FEE, SLIP

    for i in range(warm, i1):
        # update MFE/MAE for open positions (path after entry — diagnóstico)
        for sym, op in list(aux.opens.items()):
            bar = data[sym][i]
            hi, lo = float(bar["high"]), float(bar["low"])
            fav = (hi / op.entry_px) - 1.0
            adv = 1.0 - (lo / op.entry_px)
            op.mfe = max(op.mfe, fav)
            op.mae = max(op.mae, adv)

        marks = {s: float(data[s][i]["close"]) for s in data}
        equity = book.mark_equity(marks)
        book.peak = max(book.peak, equity)
        pause = equity <= book.peak * 0.97
        invested = sum(p.cost for p in book.positions.values())

        for sym in list(book.positions.keys()):
            c = data[sym][: i + 1]
            entry = book.positions[sym].entry
            mark = float(c[-1]["close"])
            action, reason = _exit_signal(variant, c, entry, mark, bar_minutes=bar_minutes)
            if action == "SELL":
                before = book.realized
                fee = fee_def if variant != "A_BASELINE" else A_FEE
                slip = slip_def if variant != "A_BASELINE" else A_SLIP
                _fill_sell(book, sym, mark, fee, slip)
                delta = book.realized - before
                op = aux.opens.pop(sym, None)
                dur = (i - op.entry_i) if op else None
                gross = (mark - (op.entry_px if op else entry)) * (op.qty if op else 0)
                aux.trades.append(
                    {
                        "symbol": sym,
                        "variant": variant,
                        "entry_i": op.entry_i if op else None,
                        "exit_i": i,
                        "entry_px": op.entry_px if op else entry,
                        "exit_px": mark,
                        "qty": op.qty if op else None,
                        "net_pnl": round(delta, 6),
                        "gross_price_move_usdt": round(gross, 6) if op else None,
                        "mfe": round(op.mfe, 6) if op else None,
                        "mae": round(op.mae, 6) if op else None,
                        "duration_bars": dur,
                        "duration_hours": (dur * bar_minutes / 60.0) if dur is not None else None,
                        "exit_reason": reason,
                        "entry_reason": op.reason if op else None,
                        "regime_tv": op.regime_tv if op else None,
                        "volume": op.volume if op else None,
                        "hour_utc": op.hour_utc if op else None,
                        "rr_realized": round(delta / max((op.mae * op.entry_px * (op.qty or 0)), 1e-9), 4)
                        if op and op.mae > 0
                        else None,
                        "left_on_table": round((op.mfe - ((mark / op.entry_px) - 1.0)), 6)
                        if op
                        else None,
                    }
                )

        if pause or len(book.positions) >= MAX_POSITIONS or invested >= MAX_EXPOSURE_USDT:
            continue

        for sym in data:
            if sym in book.positions:
                continue
            if aux.last_entry.get(sym, -10**9) > i - max(4, 12 // max(1, bar_minutes // 15)):
                continue
            c = data[sym][: i + 1]
            allow, reason, fee, slip = _entry_signal(variant, c, bar_minutes=bar_minutes)
            if not allow:
                continue
            px = float(c[-1]["close"])
            before_buys = book.buys
            if _fill_buy(book, sym, px, fee, slip, MAX_POS_USDT):
                aux.last_entry[sym] = i
                pos = book.positions[sym]
                reg = classify_regime_x(c)
                aux.opens[sym] = OpenPos(
                    symbol=sym,
                    entry_i=i,
                    entry_px=pos.entry,
                    qty=pos.qty,
                    fee_entry=fee * pos.cost,
                    slip_entry=slip * pos.cost,
                    regime_tv=reg["regime_tv"],
                    volume=reg["volume"],
                    hour_utc=reg["hour_utc"],
                    reason=reason,
                )
                assert book.buys >= before_buys

    closed = [t["net_pnl"] for t in aux.trades]
    equity = book.mark_equity({s: float(data[s][i1 - 1]["close"]) for s in data})
    return {
        "variant": variant,
        "trades": aux.trades,
        "n": len(aux.trades),
        "net_pnl_sum": round(sum(closed), 6),
        "expectancy": round(sum(closed) / len(closed), 6) if closed else None,
        "win_rate": round(sum(1 for x in closed if x > 0) / len(closed), 6) if closed else None,
        "fees": round(book.fees, 6),
        "slips": round(book.slips, 6),
        "equity": round(equity, 4),
        "net_vs_initial": round(equity - 1000.0, 4),
    }


def _agg_segments(trades: list[dict[str, Any]], key_fn) -> dict[str, Any]:
    buckets: dict[str, list[float]] = {}
    meta: dict[str, list[dict]] = {}
    for t in trades:
        k = key_fn(t)
        if k is None:
            continue
        buckets.setdefault(k, []).append(float(t["net_pnl"]))
        meta.setdefault(k, []).append(t)
    out = {}
    for k, pnls in buckets.items():
        n = len(pnls)
        wins = [x for x in pnls if x > 0]
        losses = [x for x in pnls if x < 0]
        gl = abs(sum(losses))
        mfes = [float(t["mfe"]) for t in meta[k] if t.get("mfe") is not None]
        maes = [float(t["mae"]) for t in meta[k] if t.get("mae") is not None]
        left = [float(t["left_on_table"]) for t in meta[k] if t.get("left_on_table") is not None]
        out[k] = {
            "n": n,
            "sufficient_n": n >= MIN_SEGMENT_N,
            "net_pnl_sum": round(sum(pnls), 6),
            "expectancy": round(sum(pnls) / n, 6) if n else None,
            "win_rate": round(len(wins) / n, 6) if n else None,
            "profit_factor": round(sum(wins) / gl, 6) if gl > 0 else None,
            "avg_mfe": round(sum(mfes) / len(mfes), 6) if mfes else None,
            "avg_mae": round(sum(maes) / len(maes), 6) if maes else None,
            "avg_left_on_table": round(sum(left) / len(left), 6) if left else None,
            "exit_reasons": _count([t.get("exit_reason") for t in meta[k]]),
        }
    return out


def _count(xs: list[Any]) -> dict[str, int]:
    d: dict[str, int] = {}
    for x in xs:
        k = str(x or "unknown")
        d[k] = d.get(k, 0) + 1
    return d


def block_bootstrap_expectancy(pnls: list[float], *, block: int = 5, n_boot: int = 400, seed: int = 42) -> dict[str, Any]:
    if len(pnls) < block * 2:
        return {"ok": False, "reason": "sample_too_small"}
    rng = random.Random(seed)
    means = []
    n = len(pnls)
    for _ in range(n_boot):
        sample = []
        while len(sample) < n:
            start = rng.randrange(0, n - block + 1)
            sample.extend(pnls[start : start + block])
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return {
        "ok": True,
        "mean": round(sum(pnls) / n, 6),
        "ci95": [round(lo, 6), round(hi, 6)],
        "p_positive_proxy": round(sum(1 for m in means if m > 0) / n_boot, 4),
        "block": block,
        "n_boot": n_boot,
        "note": "Bootstrap por bloques; dependencia temporal aproximada. No es p-value exacto.",
    }


def evaluate_hypotheses(by_variant_regime: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for h in HYPOTHESES:
        vid = h["variant"]
        segs = by_variant_regime.get(vid) or {}
        if h.get("regime_tv"):
            seg = segs.get(h["regime_tv"])
        else:
            # prefix aggregate
            prefix = h.get("regime_tv_prefix") or ""
            pnls_n = 0
            exp_num = 0.0
            exp_den = 0
            for rk, s in segs.items():
                if str(rk).startswith(prefix) and s.get("sufficient_n"):
                    pnls_n += int(s["n"])
                    if s.get("expectancy") is not None:
                        exp_num += float(s["expectancy"]) * int(s["n"])
                        exp_den += int(s["n"])
            seg = {
                "n": pnls_n,
                "sufficient_n": pnls_n >= MIN_SEGMENT_N,
                "expectancy": (exp_num / exp_den) if exp_den else None,
            }
        status = "inconclusive"
        detail = ""
        if not seg or not seg.get("sufficient_n"):
            status = "insufficient_n"
            detail = f"N={seg.get('n') if seg else 0} < {MIN_SEGMENT_N}"
        elif h["expect"] == "positive_expectancy":
            ok = (seg.get("expectancy") or 0) > 0
            status = "supported" if ok else "rejected"
            detail = f"expectancy={seg.get('expectancy')} USDT/op"
        elif h["expect"] == "worse_than_overall":
            # compared later in report; mark as observational
            status = "observational"
            detail = f"expectancy_segment={seg.get('expectancy')}"
        results.append({**h, "status": status, "detail": detail, "segment": seg})
    return results


def run_diagnose_x(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    coverage = {s: summarize_symbol(s, "1m") for s in symbols}
    data = load_multi_symbol_bars(symbols, "1h")
    if not data:
        return {
            "available": False,
            "reason": "historial_insuficiente",
            "paper_only": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    n = min(len(v) for v in data.values())
    # Misma partición W: 70/20/10 — holdout W CONSUMIDO (no re-seleccionar)
    is_end = int(n * 0.70)
    oos_end = int(n * 0.90)
    hold_end = n

    # Distribución de regímenes (BTC como referencia de mercado)
    regime_bars = regime_histogram(data["BTCUSDT"], step=1)

    variants = ["A_BASELINE", "V_TREND", "V_BREAK", "V_MEAN"]
    # Exploración en IS+OOS combinados (sin holdout) — hipótesis predefinidas
    explore_end = oos_end
    per_variant = {}
    by_regime: dict[str, dict[str, Any]] = {}
    by_symbol: dict[str, dict[str, Any]] = {}
    by_hour: dict[str, dict[str, Any]] = {}
    signal_quality: dict[str, Any] = {}
    boot: dict[str, Any] = {}
    cost_sens: dict[str, Any] = {}

    for v in variants:
        sim = simulate_trades(data, variant=v, i0=80, i1=explore_end, bar_minutes=60)
        trades = sim["trades"]
        per_variant[v] = {k: sim[k] for k in sim if k != "trades"}
        by_regime[v] = _agg_segments(trades, lambda t: t.get("regime_tv"))
        by_symbol[v] = _agg_segments(trades, lambda t: t.get("symbol"))
        by_hour[v] = _agg_segments(
            trades, lambda t: f"h{int(t['hour_utc']):02d}" if t.get("hour_utc") is not None else None
        )
        # calidad de señales
        if trades:
            mfe = [float(t["mfe"]) for t in trades if t.get("mfe") is not None]
            mae = [float(t["mae"]) for t in trades if t.get("mae") is not None]
            left = [float(t["left_on_table"]) for t in trades if t.get("left_on_table") is not None]
            nets = [float(t["net_pnl"]) for t in trades]
            # entrada vs salida: si avg MFE >> resultado, salidas dejan dinero; si MAE alto y net neg, entradas malas
            avg_mfe = sum(mfe) / len(mfe) if mfe else None
            avg_mae = sum(mae) / len(mae) if mae else None
            avg_net_frac = None
            if trades:
                fracs = []
                for t in trades:
                    if t.get("entry_px"):
                        fracs.append(float(t["exit_px"]) / float(t["entry_px"]) - 1.0)
                avg_net_frac = sum(fracs) / len(fracs) if fracs else None
            entry_problem = bool(avg_mae is not None and avg_mfe is not None and avg_mae > avg_mfe)
            exit_problem = bool(
                avg_mfe is not None and avg_net_frac is not None and avg_mfe > 0 and avg_net_frac < 0.3 * avg_mfe
            )
            signal_quality[v] = {
                "n": len(trades),
                "avg_mfe": round(avg_mfe, 6) if avg_mfe is not None else None,
                "avg_mae": round(avg_mae, 6) if avg_mae is not None else None,
                "avg_left_on_table": round(sum(left) / len(left), 6) if left else None,
                "avg_capture_frac": round(avg_net_frac, 6) if avg_net_frac is not None else None,
                "suggest_entry_issue": entry_problem,
                "suggest_exit_issue": exit_problem,
                "exit_reasons": _count([t.get("exit_reason") for t in trades]),
                "note": (
                    "MFE/MAE son métricas diagnósticas de trayectoria post-entrada; "
                    "no se usaron para decidir la entrada."
                ),
            }
            boot[v] = block_bootstrap_expectancy(nets, block=5, n_boot=400)
        else:
            signal_quality[v] = {"n": 0}
            boot[v] = {"ok": False, "reason": "no_trades"}

        # sensibilidad de costos: re-simular con 1.5× fee+slip solo en métrica agregada
        # (aproximación: escalar costos reportados; no re-optimiza)
        cost_sens[v] = {
            "base_fees": sim["fees"],
            "base_slips": sim["slips"],
            "base_net": sim["net_vs_initial"],
            "stressed_cost_drag_1_5x_usdt": round(1.5 * (sim["fees"] + sim["slips"]) - (sim["fees"] + sim["slips"]), 4),
            "note": "Drag adicional teórico 1.5× costos; no implica re-simulación tick a tick.",
        }

    # Holdout W: solo reportar que está consumido; no usarlo para crownear
    holdout_note = {
        "consumed": HOLDOUT_W_CONSUMED,
        "range_bars": [oos_end, hold_end],
        "policy": (
            "El 10% final ya se inspeccionó en Etapa W. "
            "No se reutiliza para seleccionar estrategias en Etapa X. "
            "Validación independiente requiere datos posteriores a 2025-10-31."
        ),
    }

    hyp = evaluate_hypotheses(by_regime)

    # Segmentos con expectancy >0 y N suficiente (exploratorio — corrección Bonferroni grosera)
    positive_segments = []
    n_tests = 0
    for v, segs in by_regime.items():
        for rk, s in segs.items():
            n_tests += 1
            if s.get("sufficient_n") and (s.get("expectancy") or 0) > 0:
                positive_segments.append({"variant": v, "regime_tv": rk, **s})
    # Bonferroni: alpha 0.05 / n_tests on bootstrap p_positive if available
    for p in positive_segments:
        b = boot.get(p["variant"]) or {}
        p["multiple_testing_note"] = (
            f"Se exploraron ~{n_tests} segmentos régimen×estrategia; "
            "un segmento positivo aislado puede ser selección retrospectiva."
        )
        p["bootstrap"] = b if b.get("ok") else None

    # buy&hold / cash
    bh0 = sum(float(data[s][80]["close"]) for s in data) / len(data)
    bh1 = sum(float(data[s][explore_end - 1]["close"]) for s in data) / len(data)

    first_t = int(data[symbols[0]][0]["open_time"])
    last_t = int(data[symbols[0]][-1]["open_time"])

    # Verdict
    robust_positive = [
        p
        for p in positive_segments
        if p.get("n", 0) >= MIN_SEGMENT_N
        and (p.get("bootstrap") or {}).get("ci95", [0, 0])[0] > 0
    ]

    return {
        "etapa": "X",
        "paper_only": True,
        "available": True,
        "units": _units_note(),
        "data_confirmation": {
            "source": "parquet_binance_vision",
            "interval_sim": "1h",
            "bars_per_symbol": n,
            "not_rest_limit_1000": n > 1000,
            "span": {
                "first_iso": datetime.fromtimestamp(first_t / 1000, tz=timezone.utc).isoformat(),
                "last_iso": datetime.fromtimestamp(last_t / 1000, tz=timezone.utc).isoformat(),
            },
            "coverage_1m": {
                s: {
                    "n_bars": coverage[s].get("n_bars"),
                    "verified": coverage[s].get("verified"),
                    "coverage_pct": coverage[s].get("coverage_pct"),
                }
                for s in symbols
            },
        },
        "hypotheses_predefined": HYPOTHESES,
        "hypotheses_results": hyp,
        "regime_bar_counts_btc": regime_bars,
        "walk_forward": {
            "is_end": is_end,
            "oos_end": oos_end,
            "holdout_end": hold_end,
            "exploration_uses": "IS+OOS (bars 80..oos_end), holdout excluded",
        },
        "holdout_w": holdout_note,
        "per_variant": per_variant,
        "by_regime": by_regime,
        "by_symbol": by_symbol,
        "by_hour": by_hour,
        "signal_quality": signal_quality,
        "bootstrap": boot,
        "cost_sensitivity": cost_sens,
        "positive_segments_exploratory": positive_segments,
        "robust_positive_segments": robust_positive,
        "benchmarks": {
            "cash_net_usdt": 0.0,
            "buy_hold_proxy_return": round(bh1 / bh0 - 1.0, 6) if bh0 else None,
        },
        "min_segment_n": MIN_SEGMENT_N,
        "claim": {
            "declare_profitable": False,
            "activate_strategy": False,
            "reason": (
                "Ningún segmento se promociona automáticamente. "
                + (
                    "No hay segmentos con CI bootstrap>0 y N suficiente."
                    if not robust_positive
                    else "Hay segmentos exploratorios positivos; requieren validación en datos post-2025-10."
                )
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = p.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(json.dumps(run_diagnose_x(symbols), indent=2, default=str))


if __name__ == "__main__":
    main()
