"""Etapa Y — salidas, captura MFE/MAE y costos. Entradas A/V-BREAK fijas.

Event-driven: señal en 1h cerrada; trayectoria/salida en 1m.
Misma lista de entradas para Y0–Y4 (comparación causal de salidas).
Intrabar ambiguo: SL antes que TP (conservador).
Holdout W consumido; post-2025-10 no disponible en repo.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ...active.backtest_b import Book, _fill_buy, _fill_sell
from ...demo.indicators import compute_bundle as compute_a
from ...demo.policy import BUY_MIN_FLAGS, BUY_SCORE_MIN, FEE_RATE as A_FEE, SLIP_RATE as A_SLIP
from ..policies_v import FEE_RATE, MAX_EXPOSURE_USDT, MAX_POS_USDT, MAX_POSITIONS, SLIP_RATE
from ..regimes import _atr_pct
from .backtest_w import _agg_n, load_multi_symbol_bars
from .coverage import summarize_symbol
from .regimes_x import classify_regime_x
from .store import load_range

MIN_N = 30
MAX_HOLD_1M = 48 * 60
TREND_CHECK_EVERY = 5  # minutos: SL/TP cada 1m; invalidación de tendencia cada 5m
FEE, SLIP = FEE_RATE, SLIP_RATE

Y_POLICIES = {
    "Y0": {"title": "Salida original", "frozen": True, "human": "Reglas actuales A / V-BREAK."},
    "Y1": {
        "title": "Tendencia con confirmación",
        "frozen": True,
        "confirm_bars": 2,
        "human": "Invalidación requiere 2 comprobaciones consecutivas; SL de protección intacto.",
    },
    "Y2": {
        "title": "Trailing ATR",
        "frozen": True,
        "atr_n": 14,
        "atr_mult": 2.0,
        "emergency_sl": 0.015,
        "human": "Trail = pico − 2×ATR%; emergencia −1.5%.",
    },
    "Y3": {
        "title": "Salida por tiempo",
        "frozen": True,
        "max_hold_1m": 24 * 60,
        "emergency_sl": 0.015,
        "human": "Cierra a 24h o SL emergencia −1.5%.",
    },
    "Y4": {
        "title": "SL/TP congelados",
        "frozen": True,
        "sl": 0.012,
        "tp": 0.020,
        "human": "Stop −1.2% y take +2.0% fijos.",
    },
}


@dataclass
class Entry:
    symbol: str
    i1h: int
    entry_i1m: int
    signal_px: float
    regime_tv: str
    entry_reason: str
    fee: float
    slip: float


@dataclass
class Pos:
    symbol: str
    entry_i1m: int
    entry_px: float
    fee: float
    slip: float
    regime_tv: str
    entry_reason: str
    peak_px: float
    confirm: int = 0
    trail: float | None = None


def _cost_rt(fee: float, slip: float) -> float:
    return 2.0 * (fee + slip)


def _entry_a(c1h: list[dict]) -> tuple[bool, str]:
    b = compute_a(c1h[-120:], c1h[-80:])
    if b and int(b["flags_true"]) >= BUY_MIN_FLAGS and float(b["signal_score"]) >= BUY_SCORE_MIN:
        return True, "demo_buy"
    return False, "no_signal"


def _entry_vbreak(c1h: list[dict], fee: float, slip: float) -> tuple[bool, str]:
    if len(c1h) < 13:
        return False, "no_signal"
    window = c1h[-13:-1]
    hi = max(float(x["high"]) for x in window)
    vols = [float(x["volume"]) for x in c1h]
    sma_vol = sum(vols[-20:]) / 20 if len(vols) >= 20 else 0.0
    close = float(c1h[-1]["close"])
    vol = float(c1h[-1]["volume"])
    atr_pct = (hi - min(float(x["low"]) for x in window)) / close if close else 0.0
    if close > hi and vol > 1.2 * sma_vol and atr_pct >= 1.2 * (fee + slip):
        return True, "v_break_entry"
    return False, "no_signal"


def _intrabar(bar: dict, sl_px: float | None, tp_px: float | None) -> tuple[str | None, float]:
    lo, hi, close = float(bar["low"]), float(bar["high"]), float(bar["close"])
    hit_sl = sl_px is not None and lo <= sl_px
    hit_tp = tp_px is not None and hi >= tp_px
    if hit_sl and hit_tp:
        return "sl_conservative_intrabar", float(sl_px)
    if hit_sl:
        return "sl", float(sl_px)
    if hit_tp:
        return "tp", float(tp_px)
    return None, close


def _path_stats(path: list[dict], entry_px: float) -> dict[str, Any]:
    mfe = mae = 0.0
    t_mfe = t_mae = 0
    for i, b in enumerate(path):
        fav = float(b["high"]) / entry_px - 1.0
        adv = 1.0 - float(b["low"]) / entry_px
        if fav > mfe:
            mfe, t_mfe = fav, i
        if adv > mae:
            mae, t_mae = adv, i
    return {
        "mfe": round(mfe, 6),
        "mae": round(mae, 6),
        "time_to_mfe_min": t_mfe,
        "time_to_mae_min": t_mae,
        "path_len_min": len(path),
    }


def _manage_until_exit(
    rows_1m: list[dict],
    pos: Pos,
    *,
    entry_mode: str,
    exit_id: str,
) -> tuple[float, str, list[dict]]:
    path: list[dict] = []
    j1 = min(len(rows_1m), pos.entry_i1m + 1 + MAX_HOLD_1M)
    for j in range(pos.entry_i1m + 1, j1):
        bar = rows_1m[j]
        path.append(bar)
        hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        pos.peak_px = max(pos.peak_px, hi)
        hold = j - pos.entry_i1m
        do_trend = (hold % TREND_CHECK_EVERY == 0) or hold < 3

        if exit_id == "Y0":
            if entry_mode == "A_BASELINE":
                hit, px = _intrabar(bar, pos.entry_px * 0.99, pos.entry_px * 1.02)
                if hit:
                    reason = "stop_loss_1pct" if hit.startswith("sl") else "take_profit_2pct"
                    return px, reason, path
                if do_trend:
                    win = rows_1m[max(0, j - 120) : j + 1]
                    b = compute_a(win, win[-80:] if len(win) >= 80 else win)
                    if b and b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42:
                        return close, "trend_break_1m", path
            else:
                # Necesita ≥13×15m: lookback ≥ 15*20 minutos (no solo 120).
                win = rows_1m[max(0, j - 15 * 20) : j + 1]
                c15 = _agg_n(win, 15)
                sl_px = tp_px = None
                if len(c15) >= 13:
                    w = c15[-13:-1]
                    lo_r = min(float(x["low"]) for x in w)
                    hi_r = max(float(x["high"]) for x in w)
                    rng = max(hi_r - lo_r, pos.entry_px * 0.002)
                    sl_px = max(lo_r, pos.entry_px * (1 - 0.02))
                    tp_px = pos.entry_px + min(1.5 * rng, pos.entry_px * 0.03)
                hit, px = _intrabar(bar, sl_px, tp_px)
                if hit:
                    return px, ("sl_range" if hit.startswith("sl") else "tp_range"), path

        elif exit_id == "Y1":
            sl = pos.entry_px * (0.99 if entry_mode == "A_BASELINE" else 0.98)
            if lo <= sl:
                return sl, "sl_protection", path
            if entry_mode == "A_BASELINE":
                if hi >= pos.entry_px * 1.02:
                    return pos.entry_px * 1.02, "take_profit_2pct", path
                weak = False
                if do_trend:
                    win = rows_1m[max(0, j - 120) : j + 1]
                    b = compute_a(win, win[-80:] if len(win) >= 80 else win)
                    weak = bool(b and b["ema9_1m"] < b["ema21_1m"] and float(b["rsi14_1m"]) < 42)
            else:
                weak = False
                if do_trend:
                    win = rows_1m[max(0, j - 15 * 20) : j + 1]
                    c15 = _agg_n(win, 15)
                    if len(c15) >= 13:
                        lo_r = min(float(x["low"]) for x in c15[-13:-1])
                        weak = close < lo_r
            if do_trend:
                pos.confirm = pos.confirm + 1 if weak else 0
            if pos.confirm >= int(Y_POLICIES["Y1"]["confirm_bars"]):
                return close, "trend_confirm_exit", path

        elif exit_id == "Y2":
            em = pos.entry_px * (1 - float(Y_POLICIES["Y2"]["emergency_sl"]))
            if do_trend or pos.trail is None:
                win = rows_1m[max(0, j - 40) : j + 1]
                atrp = _atr_pct(win, int(Y_POLICIES["Y2"]["atr_n"])) or 0.005
                cand = pos.peak_px * (1 - float(Y_POLICIES["Y2"]["atr_mult"]) * atrp)
                pos.trail = max(pos.trail or cand, cand)
            stop = max(em, pos.trail or em)
            hit, px = _intrabar(bar, stop, None)
            if hit:
                return px, "atr_trail_or_emergency", path

        elif exit_id == "Y3":
            em = pos.entry_px * (1 - float(Y_POLICIES["Y3"]["emergency_sl"]))
            if lo <= em:
                return em, "sl_emergency", path
            if hold >= int(Y_POLICIES["Y3"]["max_hold_1m"]):
                return close, "time_exit_24h", path

        elif exit_id == "Y4":
            sl = pos.entry_px * (1 - float(Y_POLICIES["Y4"]["sl"]))
            tp = pos.entry_px * (1 + float(Y_POLICIES["Y4"]["tp"]))
            hit, px = _intrabar(bar, sl, tp)
            if hit:
                return px, hit, path

        if hold >= MAX_HOLD_1M:
            return close, "max_hold_48h", path

    last = rows_1m[min(len(rows_1m) - 1, j1 - 1)]
    return float(last["close"]), "eod_force", path


def collect_entries(
    data_1h: dict[str, list[dict]],
    idx_1m: dict[str, dict[int, int]],
    *,
    entry_mode: str,
    i0: int,
    i1: int,
) -> list[Entry]:
    """Entradas fijas (cooldown 4h, máx posiciones/exposición) independientes de la salida."""
    fee0, slip0 = (A_FEE, A_SLIP) if entry_mode == "A_BASELINE" else (FEE, SLIP)
    last_entry = {s: -10**9 for s in data_1h}
    open_slots: dict[str, int] = {}  # symbol -> free_at_1h_index (proxy 6h hold for inventory)
    entries: list[Entry] = []
    warm = max(80, i0)
    cash_proxy = 1000.0
    invested = 0.0
    n_open = 0

    for i in range(warm, i1):
        # liberar slots proxy
        for sym, free_i in list(open_slots.items()):
            if i >= free_i:
                del open_slots[sym]
                n_open = max(0, n_open - 1)
                invested = max(0.0, invested - MAX_POS_USDT)

        if n_open >= MAX_POSITIONS or invested >= MAX_EXPOSURE_USDT:
            continue

        for sym in data_1h:
            if sym in open_slots:
                continue
            if i - last_entry[sym] < 4:
                continue
            c = data_1h[sym][: i + 1]
            if entry_mode == "A_BASELINE":
                allow, reason = _entry_a(c)
                fee, slip = A_FEE, A_SLIP
            else:
                allow, reason = _entry_vbreak(c, FEE, SLIP)
                fee, slip = FEE, SLIP
            if not allow:
                continue
            px = float(c[-1]["close"])
            ot = int(c[-1]["open_time"])
            j = idx_1m[sym].get(ot + 59 * 60_000, idx_1m[sym].get(ot))
            if j is None:
                continue
            # proxy fill affordability
            if cash_proxy - invested < MAX_POS_USDT * 0.5:
                continue
            last_entry[sym] = i
            open_slots[sym] = i + 6  # ~6h occupancy proxy so entries comparable across exits
            n_open += 1
            invested += MAX_POS_USDT
            entries.append(
                Entry(
                    symbol=sym,
                    i1h=i,
                    entry_i1m=j,
                    signal_px=px,
                    regime_tv=classify_regime_x(c)["regime_tv"],
                    entry_reason=reason,
                    fee=fee,
                    slip=slip,
                )
            )
            if n_open >= MAX_POSITIONS or invested >= MAX_EXPOSURE_USDT:
                break
    _ = fee0, slip0
    return entries


def simulate_exits_on_entries(
    entries: list[Entry],
    data_1h: dict[str, list[dict]],
    data_1m: dict[str, list[dict]],
    *,
    entry_mode: str,
    exit_id: str,
) -> dict[str, Any]:
    book = Book()
    trades: list[dict[str, Any]] = []
    peak_eq = 1000.0
    max_dd = 0.0
    for e in entries:
        px = e.signal_px
        if not _fill_buy(book, e.symbol, px, e.fee, e.slip, MAX_POS_USDT):
            continue
        p = book.positions[e.symbol]
        pos = Pos(
            symbol=e.symbol,
            entry_i1m=e.entry_i1m,
            entry_px=p.entry,
            fee=e.fee,
            slip=e.slip,
            regime_tv=e.regime_tv,
            entry_reason=e.entry_reason,
            peak_px=p.entry,
        )
        exit_px, exit_reason, path = _manage_until_exit(
            data_1m[e.symbol], pos, entry_mode=entry_mode, exit_id=exit_id
        )
        before = book.realized
        _fill_sell(book, e.symbol, exit_px, e.fee, e.slip)
        net = book.realized - before
        eq = 1000.0 + book.realized
        peak_eq = max(peak_eq, eq)
        max_dd = max(max_dd, 1.0 - (eq / peak_eq) if peak_eq else 0.0)
        stats = _path_stats(path, pos.entry_px)
        captured = exit_px / pos.entry_px - 1.0
        crt = _cost_rt(e.fee, e.slip)
        trades.append(
            {
                "symbol": e.symbol,
                "entry_mode": entry_mode,
                "exit_policy": exit_id,
                "entry_px": pos.entry_px,
                "exit_px": exit_px,
                "net_pnl": round(net, 6),
                "captured_frac": round(captured, 6),
                "exit_reason": exit_reason,
                "entry_reason": e.entry_reason,
                "regime_tv": e.regime_tv,
                "duration_min": len(path),
                "costs_rt_frac": round(crt, 6),
                "mfe_gt_costs": stats["mfe"] > crt,
                "gave_back_to_loss": stats["mfe"] > crt and net < 0,
                "capture_ratio": round(captured / stats["mfe"], 4) if stats["mfe"] > 1e-9 else None,
                **stats,
            }
        )

    nets = [t["net_pnl"] for t in trades]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x < 0]
    gl = abs(sum(losses))
    equity = 1000.0 + book.realized
    mfe_ok = sum(1 for t in trades if t["mfe_gt_costs"])
    gave = sum(1 for t in trades if t["gave_back_to_loss"])
    caps = [t["capture_ratio"] for t in trades if t.get("capture_ratio") is not None]
    trend_ex = sum(1 for t in trades if "trend" in str(t["exit_reason"]))
    by_reg: dict[str, list[float]] = {}
    for t in trades:
        by_reg.setdefault(t["regime_tv"], []).append(t["net_pnl"])
    return {
        "entry_mode": entry_mode,
        "exit_policy": exit_id,
        "n": len(trades),
        "n_entries_fixed": len(entries),
        "net_vs_initial": round(equity - 1000.0, 4),
        "net_pnl_sum": round(sum(nets), 6) if nets else 0.0,
        "expectancy": round(sum(nets) / len(nets), 6) if nets else None,
        "win_rate": round(len(wins) / len(nets), 6) if nets else None,
        "profit_factor": round(sum(wins) / gl, 6) if gl > 0 else None,
        "max_drawdown_proxy": round(max_dd, 6),
        "fees": round(book.fees, 6),
        "slips": round(book.slips, 6),
        "pct_mfe_gt_costs": round(mfe_ok / len(trades), 4) if trades else None,
        "pct_gave_back_to_loss": round(gave / len(trades), 4) if trades else None,
        "avg_capture_ratio": round(sum(caps) / len(caps), 4) if caps else None,
        "pct_trend_noise_exits": round(trend_ex / len(trades), 4) if trades else None,
        "avg_duration_min": round(sum(t["duration_min"] for t in trades) / len(trades), 2) if trades else None,
        "avg_mfe": round(sum(t["mfe"] for t in trades) / len(trades), 6) if trades else None,
        "avg_mae": round(sum(t["mae"] for t in trades) / len(trades), 6) if trades else None,
        "by_regime": {
            k: {
                "n": len(xs),
                "sufficient_n": len(xs) >= MIN_N,
                "expectancy": round(sum(xs) / len(xs), 6),
                "net_pnl_sum": round(sum(xs), 6),
            }
            for k, xs in by_reg.items()
        },
        "exit_reasons": _count([t["exit_reason"] for t in trades]),
        "sufficient_n": len(trades) >= MIN_N,
        "trades_sample": trades[:5],
    }


def _count(xs: list[str]) -> dict[str, int]:
    d: dict[str, int] = {}
    for x in xs:
        d[x] = d.get(x, 0) + 1
    return d


def run_etapa_y(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    cov = {s: summarize_symbol(s, "1m") for s in symbols}
    data_1h = load_multi_symbol_bars(symbols, "1h")
    if not data_1h:
        return {"available": False, "reason": "no_1h", "paper_only": True}

    data_1m = {}
    for s in symbols:
        rows = load_range(s, "1m")
        if len(rows) < 10_000:
            return {"available": False, "reason": f"1m_insufficient:{s}", "paper_only": True}
        data_1m[s] = rows
    n1 = min(len(v) for v in data_1m.values())
    data_1m = {s: v[-n1:] for s, v in data_1m.items()}
    idx_1m = {s: {int(b["open_time"]): i for i, b in enumerate(rows)} for s, rows in data_1m.items()}

    n = min(len(v) for v in data_1h.values())
    is_end = int(n * 0.70)
    explore_end = int(n * 0.90)  # exclude consumed holdout

    results: dict[str, Any] = {}
    for entry_mode in ("A_BASELINE", "V_BREAK"):
        entries_is = collect_entries(
            data_1h, idx_1m, entry_mode=entry_mode, i0=80, i1=is_end
        )
        entries_oos = collect_entries(
            data_1h, idx_1m, entry_mode=entry_mode, i0=is_end, i1=explore_end
        )
        results[entry_mode] = {}
        for yid in ("Y0", "Y1", "Y2", "Y3", "Y4"):
            is_r = simulate_exits_on_entries(
                entries_is, data_1h, data_1m, entry_mode=entry_mode, exit_id=yid
            )
            oos_r = simulate_exits_on_entries(
                entries_oos, data_1h, data_1m, entry_mode=entry_mode, exit_id=yid
            )
            drag = 0.5 * (oos_r["fees"] + oos_r["slips"])
            results[entry_mode][yid] = {
                "policy": Y_POLICIES[yid],
                "in_sample": {k: is_r[k] for k in is_r if k not in {"trades_sample", "by_regime", "exit_reasons"}},
                "out_of_sample": oos_r,
                "cost_stress_oos_net_proxy": round((oos_r.get("net_vs_initial") or 0) - drag, 4),
                "fixed_entries": {"is": len(entries_is), "oos": len(entries_oos)},
            }

    candidates = []
    for entry_mode, ys in results.items():
        y0 = ys["Y0"]["out_of_sample"]
        for yid, pack in ys.items():
            if yid == "Y0":
                continue
            o = pack["out_of_sample"]
            notes: list[str] = []
            ok = True
            if not o.get("sufficient_n"):
                ok, notes = False, notes + ["pocas_ops"]
            if (o.get("net_vs_initial") or 0) <= (y0.get("net_vs_initial") or 0):
                ok, notes = False, notes + ["no_mejora_neto_vs_Y0"]
            dd0 = y0.get("max_drawdown_proxy") or 0.01
            if (o.get("max_drawdown_proxy") or 0) > max(0.05, 1.25 * dd0):
                ok, notes = False, notes + ["drawdown_peor"]
            if (pack.get("cost_stress_oos_net_proxy") or 0) <= (y0.get("net_vs_initial") or 0):
                ok, notes = False, notes + ["sensible_a_costos"]
            dur0 = y0.get("avg_duration_min") or 1.0
            dur = o.get("avg_duration_min") or 0.0
            if dur > max(180.0, 3.0 * dur0):
                ok, notes = False, notes + ["exposicion_desproporcionada"]
            if (o.get("expectancy") or 0) <= 0:
                ok, notes = False, notes + ["expectativa_no_positiva"]
            candidates.append(
                {
                    "entry_mode": entry_mode,
                    "exit_policy": yid,
                    "passes_research_filters": ok,
                    "filter_notes": notes or ["mejora_observada_sin_autorizacion"],
                    "status": "research_only_needs_auth" if ok else "rejected",
                    "promote": False,
                    "oos_net": o.get("net_vs_initial"),
                    "y0_net": y0.get("net_vs_initial"),
                }
            )

    diagnosis = {
        m: {
            "pct_mfe_gt_costs": results[m]["Y0"]["out_of_sample"].get("pct_mfe_gt_costs"),
            "pct_gave_back_to_loss": results[m]["Y0"]["out_of_sample"].get("pct_gave_back_to_loss"),
            "avg_capture_ratio": results[m]["Y0"]["out_of_sample"].get("avg_capture_ratio"),
            "pct_trend_noise_exits": results[m]["Y0"]["out_of_sample"].get("pct_trend_noise_exits"),
            "avg_duration_min": results[m]["Y0"]["out_of_sample"].get("avg_duration_min"),
            "avg_mfe": results[m]["Y0"]["out_of_sample"].get("avg_mfe"),
            "avg_mae": results[m]["Y0"]["out_of_sample"].get("avg_mae"),
            "exit_reasons": results[m]["Y0"]["out_of_sample"].get("exit_reasons"),
        }
        for m in ("A_BASELINE", "V_BREAK")
    }

    any_research = any(c["status"] == "research_only_needs_auth" for c in candidates)
    hyp = (
        "supported_for_further_research"
        if any_research
        else "not_supported_discard_minor_tweaks"
    )
    return {
        "etapa": "Y",
        "paper_only": True,
        "available": True,
        "units": {
            "net": "USDT / capital 1000",
            "mfe_mae": "fracción precio entrada",
            "mfe_disclaimer": "MFE no es ganancia garantizada ni ejecutable con certeza",
            "intrabar": "si SL y TP en misma vela 1m → SL primero",
            "entries": "lista fija por modo; solo cambia la política de salida",
            "trend_check": f"cada {TREND_CHECK_EVERY}m (SL/TP cada 1m)",
        },
        "data": {
            "coverage_1m": {s: {"n": cov[s].get("n_bars"), "verified": cov[s].get("verified")} for s in symbols},
            "bars_1h": n,
            "holdout_w_consumed": True,
            "post_oct_2025": {"available": False, "note": "Sin datos posteriores ingeridos"},
            "not_rest_1000": True,
        },
        "policies_frozen": Y_POLICIES,
        "results": results,
        "diagnosis_y0": diagnosis,
        "candidates": candidates,
        "claim": {
            "declare_profitable": False,
            "activate": False,
            "exit_fix_hypothesis": hyp,
            "reason": (
                "Hay candidata de investigación (sin activación)."
                if any_research
                else (
                    "Ninguna política Y1–Y4 mejora Y0 de forma robusta (neto, costos, exposición, "
                    "expectativa). Se descarta perseguir micro-ajustes de salida sobre las mismas entradas; "
                    "el problema fundamental sigue siendo la falta de ventaja de entrada."
                )
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    args = p.parse_args()
    print(json.dumps(run_etapa_y([s.strip() for s in args.symbols.split(",") if s.strip()]), indent=2, default=str))


if __name__ == "__main__":
    main()
