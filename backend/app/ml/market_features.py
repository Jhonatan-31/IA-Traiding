"""Cross-asset / regime features computed only from data available at decision time."""
from __future__ import annotations

import math
from typing import Any


def _align_by_open(primary: list[dict], ref: list[dict]) -> list[dict | None]:
    """Map each primary bar to ref bar with same open_time (or None)."""
    lookup = {int(r["open_time"]): r for r in ref}
    return [lookup.get(int(p["open_time"])) for p in primary]


def relative_log_return(primary_close: float, ref_close: float) -> float | None:
    if primary_close <= 0 or ref_close <= 0:
        return None
    # relative performance proxy: log(p) - log(ref) change needs series; here ratio level
    return math.log(primary_close) - math.log(ref_close)


def build_market_feature_rows(
    candles: list[dict],
    *,
    btc_candles: list[dict] | None = None,
    universe_closes_at_t: list[list[float]] | None = None,
) -> tuple[list[dict[str, float | None]], list[str]]:
    """
    Per-bar market context. universe_closes_at_t[i] = list of closes of other assets
    at the same timestamp (already aligned, causal).
    """
    names = [
        "ret_vs_btc_1",
        "mom_rel_btc_10",
        "realized_vol_norm_20",
        "atr_rel_20",
        "regime_sma50",  # 1 up, 0 flat/down
        "vol_rel_20",
        "mkt_dispersion",
        "corr_btc_20",
        "breadth_up",
    ]
    n = len(candles)
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]
    btc_aligned = _align_by_open(candles, btc_candles) if btc_candles else [None] * n

    # SMA50 for regime
    sma50: list[float | None] = [None] * n
    for i in range(n):
        if i >= 49:
            sma50[i] = sum(closes[i - 49 : i + 1]) / 50

    rows: list[dict[str, float | None]] = []
    for i in range(n):
        feat: dict[str, float | None] = {k: None for k in names}
        btc = btc_aligned[i]
        if i >= 1 and btc is not None and btc_aligned[i - 1] is not None:
            r_p = math.log(closes[i] / closes[i - 1]) if closes[i - 1] > 0 else None
            bc0 = float(btc_aligned[i - 1]["close"])  # type: ignore
            bc1 = float(btc["close"])
            r_b = math.log(bc1 / bc0) if bc0 > 0 and bc1 > 0 else None
            if r_p is not None and r_b is not None:
                feat["ret_vs_btc_1"] = r_p - r_b
        if i >= 10 and btc is not None and btc_aligned[i - 10] is not None:
            mom_p = closes[i] / closes[i - 10] - 1
            mom_b = float(btc["close"]) / float(btc_aligned[i - 10]["close"]) - 1  # type: ignore
            feat["mom_rel_btc_10"] = mom_p - mom_b
        if i >= 20:
            rets = []
            ok = True
            for j in range(i - 19, i + 1):
                if closes[j - 1] <= 0:
                    ok = False
                    break
                rets.append(math.log(closes[j] / closes[j - 1]))
            if ok and rets:
                mean = sum(rets) / len(rets)
                var = sum((x - mean) ** 2 for x in rets) / len(rets)
                rv = math.sqrt(var)
                feat["realized_vol_norm_20"] = rv
                # ATR-like range avg / close
                ranges = [
                    (highs[j] - lows[j]) / closes[j]
                    for j in range(i - 19, i + 1)
                    if closes[j] > 0
                ]
                if ranges:
                    feat["atr_rel_20"] = sum(ranges) / len(ranges)
                vma = sum(vols[i - 19 : i + 1]) / 20
                feat["vol_rel_20"] = (vols[i] / vma) if vma > 0 else None
        if sma50[i] is not None and closes[i] > 0:
            feat["regime_sma50"] = 1.0 if closes[i] > sma50[i] else 0.0  # type: ignore
        # rolling corr vs BTC
        if i >= 20 and btc_aligned[i] is not None:
            rp, rb = [], []
            good = True
            for j in range(i - 19, i + 1):
                if (
                    j < 1
                    or btc_aligned[j] is None
                    or btc_aligned[j - 1] is None
                    or closes[j - 1] <= 0
                ):
                    good = False
                    break
                rp.append(math.log(closes[j] / closes[j - 1]))
                b0 = float(btc_aligned[j - 1]["close"])  # type: ignore
                b1 = float(btc_aligned[j]["close"])  # type: ignore
                if b0 <= 0 or b1 <= 0:
                    good = False
                    break
                rb.append(math.log(b1 / b0))
            if good and len(rp) == len(rb) == 20:
                mp, mb = sum(rp) / 20, sum(rb) / 20
                cov = sum((a - mp) * (b - mb) for a, b in zip(rp, rb)) / 20
                sp = math.sqrt(sum((a - mp) ** 2 for a in rp) / 20)
                sb = math.sqrt(sum((b - mb) ** 2 for b in rb) / 20)
                feat["corr_btc_20"] = (cov / (sp * sb)) if sp > 0 and sb > 0 else None
        # cross-sectional dispersion / breadth if provided
        if universe_closes_at_t is not None and i < len(universe_closes_at_t):
            xs = [x for x in universe_closes_at_t[i] if x and x > 0]
            if len(xs) >= 3 and i >= 1 and universe_closes_at_t[i - 1]:
                prev = universe_closes_at_t[i - 1]
                rets_x = []
                for a, b in zip(xs, prev):
                    if a and b and b > 0:
                        rets_x.append(a / b - 1)
                if len(rets_x) >= 3:
                    m = sum(rets_x) / len(rets_x)
                    feat["mkt_dispersion"] = math.sqrt(
                        sum((x - m) ** 2 for x in rets_x) / len(rets_x)
                    )
                    feat["breadth_up"] = sum(1 for x in rets_x if x > 0) / len(rets_x)
        rows.append(feat)
    return rows, names


def summarize_listing_bias(per_symbol: dict[str, Any]) -> dict[str, Any]:
    """Document unequal history / survival notes from dataset quality meta."""
    starts = []
    for sym, info in per_symbol.items():
        if not isinstance(info, dict):
            continue
        start = info.get("from_ms") or info.get("from")
        if start:
            starts.append(
                {
                    "symbol": sym,
                    "from_ms": start,
                    "bars": info.get("bars"),
                }
            )
    starts.sort(key=lambda x: x["from_ms"] or 0)
    return {
        "n_symbols": len(starts),
        "earliest": starts[0] if starts else None,
        "latest_listing_proxy": starts[-1] if starts else None,
        "note": (
            "Listing dates are proxied by first available closed candle in the pull. "
            "Delisted assets absent from current Binance spot are a survival bias risk."
        ),
    }
