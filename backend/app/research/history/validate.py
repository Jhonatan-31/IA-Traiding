"""Validación OHLC / huecos / duplicados. No rellena datos ausentes."""
from __future__ import annotations

from typing import Any

from .timestamps import is_aligned_1m, normalize_open_time_ms


REQUIRED = ("open_time", "open", "high", "low", "close", "volume")


def validate_rows(
    rows: list[dict[str, Any]],
    *,
    interval_ms: int = 60_000,
    max_extreme_ret: float = 0.35,
) -> dict[str, Any]:
    """Valida filas ya parseadas. No inventa velas faltantes."""
    errors: list[str] = []
    warnings: list[str] = []
    if not rows:
        return {
            "ok": False,
            "n": 0,
            "errors": ["empty"],
            "duplicates": 0,
            "gaps": [],
            "ohlc_violations": 0,
            "extreme_moves": 0,
            "unordered": 0,
        }

    # normalize + sort check
    times: list[int] = []
    for i, r in enumerate(rows):
        for k in REQUIRED:
            if k not in r or r[k] is None:
                errors.append(f"row_{i}_missing_{k}")
                break
        try:
            t = normalize_open_time_ms(r["open_time"])
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
            v = float(r["volume"])
        except (TypeError, ValueError):
            errors.append(f"row_{i}_cast")
            continue
        if v < 0:
            errors.append(f"row_{i}_neg_vol")
        if min(o, h, l, c) <= 0:
            errors.append(f"row_{i}_non_positive_px")
        times.append(t)
        r["open_time"] = t
        r["open"], r["high"], r["low"], r["close"], r["volume"] = o, h, l, c, v

    # duplicates
    seen: set[int] = set()
    dups = 0
    uniq: list[dict[str, Any]] = []
    for r in sorted(rows, key=lambda x: int(x["open_time"])):
        t = int(r["open_time"])
        if t in seen:
            dups += 1
            continue
        seen.add(t)
        uniq.append(r)

    unordered = 0
    for i in range(1, len(times)):
        if times[i] < times[i - 1]:
            unordered += 1

    ohlc_bad = 0
    extreme = 0
    for i, r in enumerate(uniq):
        o, h, l, c = r["open"], r["high"], r["low"], r["close"]
        if h < max(o, c) or l > min(o, c) or h < l:
            ohlc_bad += 1
        if interval_ms == 60_000 and not is_aligned_1m(int(r["open_time"])):
            warnings.append(f"misaligned_1m_{r['open_time']}")
        if i > 0:
            prev = float(uniq[i - 1]["close"])
            if prev > 0 and abs(c / prev - 1.0) > max_extreme_ret:
                extreme += 1

    gaps: list[dict[str, Any]] = []
    for i in range(1, len(uniq)):
        prev_t = int(uniq[i - 1]["open_time"])
        t = int(uniq[i]["open_time"])
        delta = t - prev_t
        if delta != interval_ms:
            missing = max(0, (delta // interval_ms) - 1)
            gaps.append(
                {
                    "after": prev_t,
                    "before": t,
                    "delta_ms": delta,
                    "missing_bars_est": missing,
                }
            )

    ok = not errors and ohlc_bad == 0
    return {
        "ok": ok,
        "n": len(uniq),
        "n_raw": len(rows),
        "duplicates": dups,
        "gaps": gaps[:50],
        "gap_count": len(gaps),
        "missing_bars_est": sum(g["missing_bars_est"] for g in gaps),
        "ohlc_violations": ohlc_bad,
        "extreme_moves": extreme,
        "unordered": unordered,
        "errors": errors[:30],
        "warnings": warnings[:30],
        "first_open_time": int(uniq[0]["open_time"]) if uniq else None,
        "last_open_time": int(uniq[-1]["open_time"]) if uniq else None,
        "rows": uniq,
        "filled_fabricated": False,
        "note": "Huecos registrados; no se fabrican velas ni volumen.",
    }
