"""Informes de cobertura y calidad (disponible ≠ verificado)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .aggregate import INTERVAL_MS
from .download import disk_stats
from .store import list_partitions, load_range


def expected_1m_bars(first_ms: int, last_ms: int) -> int:
    if last_ms < first_ms:
        return 0
    return int((last_ms - first_ms) / 60_000) + 1


def summarize_symbol(symbol: str, interval: str = "1m") -> dict[str, Any]:
    parts = list_partitions(symbol, interval)
    if not parts:
        return {
            "symbol": symbol.upper(),
            "interval": interval,
            "available": False,
            "verified": False,
            "n_partitions": 0,
            "n_bars": 0,
            "note": "Sin particiones Parquet verificadas.",
        }
    n_bars = sum(int(p.get("n_bars") or 0) for p in parts)
    gap_count = sum(int((p.get("validation") or {}).get("gap_count") or 0) for p in parts)
    missing = sum(int((p.get("validation") or {}).get("missing_bars_est") or 0) for p in parts)
    dups = sum(int((p.get("validation") or {}).get("duplicates") or 0) for p in parts)
    ohlc_bad = sum(int((p.get("validation") or {}).get("ohlc_violations") or 0) for p in parts)
    oks = [bool((p.get("validation") or {}).get("ok")) for p in parts]
    firsts = [(p.get("validation") or {}).get("first_open_time") for p in parts]
    lasts = [(p.get("validation") or {}).get("last_open_time") for p in parts]
    firsts = [int(x) for x in firsts if x is not None]
    lasts = [int(x) for x in lasts if x is not None]
    first_ms = min(firsts) if firsts else None
    last_ms = max(lasts) if lasts else None
    exp = expected_1m_bars(first_ms, last_ms) if first_ms is not None and last_ms is not None else None
    # coverage vs span continuum (no fabricamos huecos)
    coverage_pct = None
    if exp and exp > 0:
        coverage_pct = round(100.0 * n_bars / exp, 4)

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "available": True,
        "verified": all(oks) and ohlc_bad == 0,
        "n_partitions": len(parts),
        "n_bars": n_bars,
        "first_open_time": first_ms,
        "last_open_time": last_ms,
        "first_iso": datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).isoformat()
        if first_ms
        else None,
        "last_iso": datetime.fromtimestamp(last_ms / 1000, tz=timezone.utc).isoformat()
        if last_ms
        else None,
        "gap_count": gap_count,
        "missing_bars_est": missing,
        "duplicates": dups,
        "ohlc_violations": ohlc_bad,
        "coverage_pct": coverage_pct,
        "expected_bars_span": exp,
        "source": "binance_vision",
        "partitions": [
            {
                "year": p["year"],
                "month": p["month"],
                "n_bars": p.get("n_bars"),
                "validation_ok": (p.get("validation") or {}).get("ok"),
                "checksum_match": (p.get("source") or {}).get("checksum_match"),
            }
            for p in parts
        ],
    }


def full_coverage_report(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    by_symbol = {s: summarize_symbol(s, "1m") for s in symbols}
    tf_counts = {}
    for s in symbols:
        for iv in INTERVAL_MS:
            if iv == "1m":
                continue
            parts = list_partitions(s, iv)
            if parts:
                tf_counts.setdefault(iv, 0)
                tf_counts[iv] += sum(int(p.get("n_bars") or 0) for p in parts)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_only": True,
        "disk": disk_stats(),
        "by_symbol": by_symbol,
        "higher_timeframes_bars": tf_counts,
        "distinction": {
            "available": "Archivos presentes en el repositorio de investigación",
            "verified": "Pasaron validación OHLC/orden/dedupe sin fabricar huecos",
        },
    }


def aligned_span_ms(symbols: list[str], interval: str = "1m") -> tuple[int, int] | None:
    spans = []
    for s in symbols:
        rep = summarize_symbol(s, interval)
        if not rep.get("first_open_time") or not rep.get("last_open_time"):
            return None
        spans.append((int(rep["first_open_time"]), int(rep["last_open_time"])))
    return max(a[0] for a in spans), min(a[1] for a in spans)
