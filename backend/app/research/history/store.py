"""Persistencia Parquet particionada (símbolo/intervalo/año/mes)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import ensure_dirs, parquet_partition
from .validate import validate_rows


def _require_pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pyarrow requerido para historial Parquet") from exc
    return pa, pq


def write_month_parquet(
    symbol: str,
    interval: str,
    year: int,
    month: int,
    rows: list[dict[str, Any]],
    *,
    interval_ms: int = 60_000,
    source_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    pa, pq = _require_pyarrow()
    report = validate_rows(rows, interval_ms=interval_ms)
    clean = report.pop("rows")
    dest = parquet_partition(symbol, interval, year, month)
    dest.parent.mkdir(parents=True, exist_ok=True)

    table = pa.table(
        {
            "open_time": [int(r["open_time"]) for r in clean],
            "open": [float(r["open"]) for r in clean],
            "high": [float(r["high"]) for r in clean],
            "low": [float(r["low"]) for r in clean],
            "close": [float(r["close"]) for r in clean],
            "volume": [float(r["volume"]) for r in clean],
            "is_closed": [True] * len(clean),
        }
    )
    tmp = dest.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    meta = {
        "symbol": symbol.upper(),
        "interval": interval,
        "year": year,
        "month": month,
        "path": str(dest),
        "n_bars": len(clean),
        "validation": {k: v for k, v in report.items() if k != "rows"},
        "parquet_sha256": digest,
        "bytes": dest.stat().st_size,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "source": source_meta or {},
        "fabricated_fills": False,
    }
    meta_path = dest.with_suffix(".meta.json")
    meta_path.write_text(__import__("json").dumps(meta, indent=2), encoding="utf-8")
    return meta


def read_month_parquet(symbol: str, interval: str, year: int, month: int) -> list[dict[str, Any]]:
    pa, pq = _require_pyarrow()
    path = parquet_partition(symbol, interval, year, month)
    if not path.exists():
        return []
    table = pq.read_table(path)
    cols = table.to_pydict()
    n = len(cols["open_time"])
    out = []
    for i in range(n):
        out.append(
            {
                "open_time": int(cols["open_time"][i]),
                "open": float(cols["open"][i]),
                "high": float(cols["high"][i]),
                "low": float(cols["low"][i]),
                "close": float(cols["close"][i]),
                "volume": float(cols["volume"][i]),
                "is_closed": True,
            }
        )
    return out


def list_partitions(symbol: str | None = None, interval: str = "1m") -> list[dict[str, Any]]:
    ensure_dirs()
    from .paths import PARQUET_DIR
    import json

    out: list[dict[str, Any]] = []
    root = PARQUET_DIR
    if not root.exists():
        return out
    for meta_path in root.rglob("part.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if symbol and meta.get("symbol") != symbol.upper():
            continue
        if meta.get("interval") != interval:
            continue
        out.append(meta)
    out.sort(key=lambda m: (m.get("symbol"), m.get("year", 0), m.get("month", 0)))
    return out


def load_range(
    symbol: str,
    interval: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Carga barras ordenadas en rango [start_ms, end_ms] inclusive por open_time."""
    parts = list_partitions(symbol, interval)
    rows: list[dict[str, Any]] = []
    for p in parts:
        month_rows = read_month_parquet(symbol, interval, int(p["year"]), int(p["month"]))
        for r in month_rows:
            t = int(r["open_time"])
            if start_ms is not None and t < start_ms:
                continue
            if end_ms is not None and t > end_ms:
                continue
            rows.append(r)
    rows.sort(key=lambda r: int(r["open_time"]))
    # dedupe by open_time
    seen: set[int] = set()
    uniq = []
    for r in rows:
        t = int(r["open_time"])
        if t in seen:
            continue
        seen.add(t)
        uniq.append(r)
    return uniq
