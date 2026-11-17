"""Ingesta Vision no destructiva: parsea columnas microestructura sin sobrescribir Parquet OHLCV V1."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Binance Vision kline CSV columns (documented order):
# open_time, open, high, low, close, volume, close_time, quote_volume,
# number_of_trades, taker_buy_base, taker_buy_quote, ignore
VISION_KLINE_FIELDS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "number_of_trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)


def parse_klines_csv_vision(raw: bytes) -> list[dict[str, Any]]:
    """Parse completo Vision. No inventa campos faltantes."""
    text = raw.decode("utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("open_time"):
            continue
        parts = line.split(",")
        if len(parts) < 6:
            continue
        row: dict[str, Any] = {
            "open_time": int(float(parts[0])),
            "open": float(parts[1]),
            "high": float(parts[2]),
            "low": float(parts[3]),
            "close": float(parts[4]),
            "volume": float(parts[5]),
            "is_closed": True,
        }
        # Extended columns only when present — never fabricate
        if len(parts) >= 8:
            row["close_time"] = int(float(parts[6]))
            row["quote_volume"] = float(parts[7])
        if len(parts) >= 9:
            row["number_of_trades"] = int(float(parts[8]))
        if len(parts) >= 11:
            row["taker_buy_base_volume"] = float(parts[9])
            row["taker_buy_quote_volume"] = float(parts[10])
        rows.append(row)
    return rows


def audit_vision_loss_vs_v1_parser(raw: bytes) -> dict[str, Any]:
    """Compara parser V1 (OHLCV-only) vs Vision extendido sobre el mismo CSV."""
    from ..research.history.download import parse_klines_csv

    v1 = parse_klines_csv(raw)
    v2 = parse_klines_csv_vision(raw)
    lost = []
    if v2 and any("quote_volume" in r for r in v2):
        lost.append("quote_volume")
    if v2 and any("number_of_trades" in r for r in v2):
        lost.append("number_of_trades")
    if v2 and any("taker_buy_base_volume" in r for r in v2):
        lost.append("taker_buy_base_volume")
    if v2 and any("taker_buy_quote_volume" in r for r in v2):
        lost.append("taker_buy_quote_volume")
    # Fields present in Vision rows but absent from V1 schema
    v1_keys = set(v1[0].keys()) if v1 else set()
    v2_keys = set()
    for r in v2[:5]:
        v2_keys |= set(r.keys())
    dropped_by_v1 = sorted(v2_keys - v1_keys)
    return {
        "n_v1": len(v1),
        "n_vision": len(v2),
        "rows_match": len(v1) == len(v2),
        "v1_omits_when_present_in_csv": dropped_by_v1,
        "microstructure_fields_detectable": lost,
        "destructive": False,
        "recommendation": (
            "Escribir sidecars *_vision_ext.parquet sin reemplazar OHLCV V1; "
            "re-ingesta opt-in por símbolo/mes."
        ),
    }


def write_vision_ext_parquet(
    symbol: str,
    interval: str,
    year: int,
    month: int,
    rows: list[dict[str, Any]],
    *,
    dest_dir: Path,
) -> dict[str, Any]:
    """Escribe Parquet extendido en ruta separada. No toca particiones V1."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pyarrow requerido") from exc

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{symbol.upper()}_{interval}_{year:04d}_{month:02d}_vision_ext.parquet"
    cols: dict[str, list] = {
        "open_time": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
        "quote_volume": [],
        "number_of_trades": [],
        "taker_buy_base_volume": [],
        "taker_buy_quote_volume": [],
        "is_closed": [],
    }
    for r in rows:
        cols["open_time"].append(int(r["open_time"]))
        cols["open"].append(float(r["open"]))
        cols["high"].append(float(r["high"]))
        cols["low"].append(float(r["low"]))
        cols["close"].append(float(r["close"]))
        cols["volume"].append(float(r["volume"]))
        cols["quote_volume"].append(float(r["quote_volume"]) if "quote_volume" in r else None)
        cols["number_of_trades"].append(
            int(r["number_of_trades"]) if "number_of_trades" in r else None
        )
        cols["taker_buy_base_volume"].append(
            float(r["taker_buy_base_volume"]) if "taker_buy_base_volume" in r else None
        )
        cols["taker_buy_quote_volume"].append(
            float(r["taker_buy_quote_volume"]) if "taker_buy_quote_volume" in r else None
        )
        cols["is_closed"].append(True)

    table = pa.table(cols)
    tmp = dest.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.replace(dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    meta = {
        "schema": "vision_ext_v1",
        "symbol": symbol.upper(),
        "interval": interval,
        "year": year,
        "month": month,
        "path": str(dest),
        "n_bars": len(rows),
        "parquet_sha256": digest,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "replaces_v1_ohlcv": False,
        "fabricated_bbo": False,
    }
    dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
