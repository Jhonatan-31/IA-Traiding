"""Rutas del repositorio histórico (bind mount /artifacts/history)."""
from __future__ import annotations

import os
from pathlib import Path

HISTORY_ROOT = Path(os.environ.get("MARKET_HISTORY_DIR", "/artifacts/history")).resolve()
RAW_DIR = HISTORY_ROOT / "raw" / "spot" / "monthly" / "klines"
PARQUET_DIR = HISTORY_ROOT / "parquet"
META_DIR = HISTORY_ROOT / "meta"
PROGRESS_PATH = META_DIR / "download_progress.json"


def ensure_dirs() -> None:
    for p in (HISTORY_ROOT, RAW_DIR, PARQUET_DIR, META_DIR):
        p.mkdir(parents=True, exist_ok=True)


def parquet_partition(symbol: str, interval: str, year: int, month: int) -> Path:
    return (
        PARQUET_DIR
        / f"symbol={symbol.upper()}"
        / f"interval={interval}"
        / f"year={year:04d}"
        / f"month={month:02d}"
        / "part.parquet"
    )


def raw_zip_path(symbol: str, interval: str, year: int, month: int) -> Path:
    name = f"{symbol.upper()}-{interval}-{year:04d}-{month:02d}.zip"
    return RAW_DIR / symbol.upper() / interval / name
