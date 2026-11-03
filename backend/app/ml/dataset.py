"""Historical closed-candle dataset builder with pagination and integrity checks."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..ohlcv import ALLOWED_INTERVALS, BASE, validate_interval, validate_symbol

DEFAULT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "ATOMUSDT",
    "NEARUSDT",
    "UNIUSDT",
    "AAVEUSDT",
]

TRAIN_INTERVALS = {"5m", "15m", "1h", "4h"}


@dataclass
class CandleRow:
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def checksum_rows(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_issues(rows: list[CandleRow]) -> dict[str, Any]:
    gaps = 0
    dupes = 0
    corrupt = 0
    seen: set[int] = set()
    prev = None
    for r in rows:
        if r.open <= 0 or r.high < r.low or r.close <= 0 or r.volume < 0:
            corrupt += 1
        if r.open_time in seen:
            dupes += 1
        seen.add(r.open_time)
        if prev is not None and r.open_time <= prev:
            gaps += 1  # non-increasing
        prev = r.open_time
    return {
        "rows": len(rows),
        "duplicates": dupes,
        "non_increasing": gaps,
        "corrupt": corrupt,
        "ok": dupes == 0 and gaps == 0 and corrupt == 0,
    }


async def fetch_klines_paginated(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    *,
    max_bars: int = 1500,
    sleep_s: float = 0.2,
) -> list[CandleRow]:
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    if interval not in TRAIN_INTERVALS:
        raise ValueError(f"train interval must be one of {sorted(TRAIN_INTERVALS)}")
    out: list[CandleRow] = []
    end_time = _now_ms()
    while len(out) < max_bars:
        limit = min(1000, max_bars - len(out))
        r = await client.get(
            BASE + "/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "endTime": end_time,
                "limit": limit,
            },
            timeout=30,
        )
        if r.status_code in (418, 429):
            time.sleep(max(sleep_s * 5, 2))
            continue
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        chunk: list[CandleRow] = []
        now = _now_ms()
        for row in batch:
            close_time = int(row[6])
            if close_time >= now:
                continue  # never include forming candle
            chunk.append(
                CandleRow(
                    symbol=symbol,
                    interval=interval,
                    open_time=int(row[0]),
                    close_time=close_time,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )
        if not chunk:
            break
        # API returns ascending; we page backward via endTime
        out = chunk + out
        end_time = chunk[0].open_time - 1
        # dedupe by open_time preserving order
        uniq: dict[int, CandleRow] = {}
        for c in out:
            uniq[c.open_time] = c
        out = [uniq[k] for k in sorted(uniq)]
        await _async_sleep(sleep_s)
        if len(batch) < limit:
            break
    return out[-max_bars:]


async def _async_sleep(s: float):
    import asyncio

    await asyncio.sleep(s)


async def build_dataset(
    *,
    symbols: list[str] | None = None,
    interval: str = "1h",
    max_bars: int = 1200,
    out_dir: Path,
) -> dict[str, Any]:
    symbols = symbols or DEFAULT_SYMBOLS
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    per_symbol: dict[str, Any] = {}
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": "ResearchPaperBot/ml-dataset"}
    ) as client:
        for sym in symbols:
            try:
                rows = await fetch_klines_paginated(
                    client, sym, interval, max_bars=max_bars
                )
                issues = detect_issues(rows)
                per_symbol[sym] = {
                    "bars": len(rows),
                    "from": rows[0].open_time if rows else None,
                    "to": rows[-1].close_time if rows else None,
                    "issues": issues,
                }
                all_rows.extend(r.as_dict() for r in rows)
            except Exception as exc:
                per_symbol[sym] = {"error": f"{type(exc).__name__}: {exc}"}

    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": BASE,
        "interval": interval,
        "symbols": symbols,
        "row_count": len(all_rows),
        "per_symbol": per_symbol,
        "closed_candles_only": True,
        "checksum": checksum_rows(all_rows),
    }
    data_path = out_dir / f"ohlcv_{interval}_{meta['checksum'][:12]}.jsonl"
    meta_path = out_dir / f"dataset_{interval}_{meta['checksum'][:12]}.meta.json"
    with data_path.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")
    meta["data_path"] = str(data_path)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["meta_path"] = str(meta_path)
    return meta


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def quality_report(rows: list[dict], interval: str) -> dict[str, Any]:
    """Per-symbol quality summary for incremental datasets."""
    by_sym: dict[str, list[dict]] = {}
    for r in rows:
        by_sym.setdefault(r["symbol"], []).append(r)
    report: dict[str, Any] = {"interval": interval, "symbols": {}, "totals": {}}
    total_gaps = 0
    total_dupes = 0
    for sym, items in sorted(by_sym.items()):
        items = sorted(items, key=lambda x: x["open_time"])
        candles = [
            CandleRow(
                symbol=sym,
                interval=interval,
                open_time=int(r["open_time"]),
                close_time=int(r["close_time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
            )
            for r in items
        ]
        issues = detect_issues(candles)
        # gap estimate by open_time steps
        step = {"5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}.get(
            interval, 3_600_000
        )
        missing = 0
        for a, b in zip(candles, candles[1:]):
            delta = b.open_time - a.open_time
            if delta > step * 1.5:
                missing += int(round(delta / step)) - 1
        total_gaps += missing
        total_dupes += issues["duplicates"]
        report["symbols"][sym] = {
            "bars": len(candles),
            "from_ms": candles[0].open_time if candles else None,
            "to_ms": candles[-1].close_time if candles else None,
            "from_utc": datetime.fromtimestamp(
                candles[0].open_time / 1000, tz=timezone.utc
            ).isoformat()
            if candles
            else None,
            "to_utc": datetime.fromtimestamp(
                candles[-1].close_time / 1000, tz=timezone.utc
            ).isoformat()
            if candles
            else None,
            "issues": issues,
            "estimated_missing_bars": missing,
        }
    report["totals"] = {
        "symbols": len(by_sym),
        "rows": len(rows),
        "estimated_missing_bars": total_gaps,
        "duplicates": total_dupes,
    }
    return report


async def build_dataset_incremental(
    *,
    symbols: list[str] | None = None,
    interval: str = "1h",
    max_bars: int = 1500,
    out_dir: Path,
    existing_path: Path | None = None,
) -> dict[str, Any]:
    """Merge new closed candles with an existing jsonl without duplicating open_times."""
    symbols = symbols or DEFAULT_SYMBOLS
    existing: list[dict] = load_jsonl(existing_path) if existing_path and existing_path.exists() else []
    by_key: dict[tuple[str, int], dict] = {
        (r["symbol"], int(r["open_time"])): r for r in existing
    }
    meta = await build_dataset(
        symbols=symbols, interval=interval, max_bars=max_bars, out_dir=out_dir
    )
    fresh = load_jsonl(Path(meta["data_path"]))
    for r in fresh:
        by_key[(r["symbol"], int(r["open_time"]))] = r
    merged = [by_key[k] for k in sorted(by_key.keys(), key=lambda x: (x[0], x[1]))]
    q = quality_report(merged, interval)
    checksum = checksum_rows(merged)
    data_path = out_dir / f"ohlcv_{interval}_{checksum[:12]}_inc.jsonl"
    with data_path.open("w", encoding="utf-8") as f:
        for row in merged:
            f.write(json.dumps(row) + "\n")
    out = {
        **meta,
        "row_count": len(merged),
        "checksum": checksum,
        "data_path": str(data_path),
        "incremental": True,
        "prior_rows": len(existing),
        "quality": q,
    }
    meta_path = out_dir / f"dataset_{interval}_{checksum[:12]}_inc.meta.json"
    meta_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    out["meta_path"] = str(meta_path)
    return out
