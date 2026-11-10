"""Descarga reanudable e idempotente desde data.binance.vision."""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .paths import META_DIR, PROGRESS_PATH, ensure_dirs, raw_zip_path
from .timestamps import normalize_open_time_ms

BASE = "https://data.binance.vision/data/spot/monthly/klines"
UA = "AITradingBotPro-ResearchHistory/etapa-w (paper-only; no trading)"


def month_url(symbol: str, interval: str, year: int, month: int) -> str:
    name = f"{symbol.upper()}-{interval}-{year:04d}-{month:02d}.zip"
    return f"{BASE}/{symbol.upper()}/{interval}/{name}"


def checksum_url(symbol: str, interval: str, year: int, month: int) -> str:
    return month_url(symbol, interval, year, month) + ".CHECKSUM"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_progress() -> dict[str, Any]:
    ensure_dirs()
    if not PROGRESS_PATH.exists():
        return {"jobs": {}, "updated_at": None}
    return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))


def save_progress(data: dict[str, Any]) -> None:
    ensure_dirs()
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = PROGRESS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS_PATH)


def job_key(symbol: str, interval: str, year: int, month: int) -> str:
    return f"{symbol.upper()}|{interval}|{year:04d}-{month:02d}"


def parse_checksum_body(text: str) -> str | None:
    # "hex  filename" or just hex
    line = (text or "").strip().splitlines()[0] if text else ""
    if not line:
        return None
    return line.split()[0].strip().lower()


def parse_klines_csv(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("open_time"):
            continue
        parts = line.split(",")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "open_time": normalize_open_time_ms(parts[0]),
                "open": float(parts[1]),
                "high": float(parts[2]),
                "low": float(parts[3]),
                "close": float(parts[4]),
                "volume": float(parts[5]),
                "is_closed": True,
            }
        )
    return rows


def extract_csv_from_zip(zip_path: Path) -> bytes:
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"no_csv_in_zip:{zip_path.name}")
        return zf.read(names[0])


async def download_month(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str,
    year: int,
    month: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Descarga un mes. Idempotente: reusa ZIP si checksum OK."""
    ensure_dirs()
    progress = load_progress()
    key = job_key(symbol, interval, year, month)
    dest = raw_zip_path(symbol, interval, year, month)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = month_url(symbol, interval, year, month)
    csum_url = checksum_url(symbol, interval, year, month)

    expected: str | None = None
    try:
        cr = await client.get(csum_url)
        if cr.status_code == 200:
            expected = parse_checksum_body(cr.text)
    except Exception as exc:
        expected = None
        progress.setdefault("jobs", {})[key] = {
            **progress.get("jobs", {}).get(key, {}),
            "checksum_fetch_error": type(exc).__name__,
        }

    if dest.exists() and not force:
        got = _sha256_file(dest)
        if expected and got == expected:
            progress.setdefault("jobs", {})[key] = {
                "status": "ready",
                "path": str(dest),
                "sha256": got,
                "checksum_match": True,
                "bytes": dest.stat().st_size,
                "source": url,
                "downloaded_at": progress.get("jobs", {}).get(key, {}).get("downloaded_at"),
            }
            save_progress(progress)
            return progress["jobs"][key]
        if expected and got != expected:
            dest.unlink(missing_ok=True)
        elif not expected:
            # sin checksum oficial: confiar si archivo > 1KB
            if dest.stat().st_size > 1000:
                progress.setdefault("jobs", {})[key] = {
                    "status": "ready_no_official_checksum",
                    "path": str(dest),
                    "sha256": got,
                    "checksum_match": None,
                    "bytes": dest.stat().st_size,
                    "source": url,
                }
                save_progress(progress)
                return progress["jobs"][key]

    # download with temp file
    tmp = dest.with_suffix(".partial")
    try:
        async with client.stream("GET", url) as resp:
            if resp.status_code == 404:
                progress.setdefault("jobs", {})[key] = {
                    "status": "missing_remote",
                    "source": url,
                    "http": 404,
                }
                save_progress(progress)
                return progress["jobs"][key]
            resp.raise_for_status()
            with tmp.open("wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
        got = _sha256_file(tmp)
        if expected and got != expected:
            tmp.unlink(missing_ok=True)
            progress.setdefault("jobs", {})[key] = {
                "status": "checksum_mismatch",
                "expected": expected,
                "got": got,
                "source": url,
            }
            save_progress(progress)
            return progress["jobs"][key]
        tmp.replace(dest)
        meta = {
            "status": "ready",
            "path": str(dest),
            "sha256": got,
            "checksum_match": (got == expected) if expected else None,
            "expected_checksum": expected,
            "bytes": dest.stat().st_size,
            "source": url,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        progress.setdefault("jobs", {})[key] = meta
        save_progress(progress)
        return meta
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        progress.setdefault("jobs", {})[key] = {
            "status": "error",
            "error": f"{type(exc).__name__}:{str(exc)[:160]}",
            "source": url,
        }
        save_progress(progress)
        return progress["jobs"][key]


async def download_range(
    symbols: list[str],
    *,
    interval: str = "1m",
    start: tuple[int, int],
    end: tuple[int, int],
    force: bool = False,
) -> dict[str, Any]:
    """Descarga meses inclusivos [start, end]."""
    ensure_dirs()
    months = iter_months(start, end)
    out: dict[str, Any] = {"months": [], "ok": 0, "fail": 0, "missing": 0}
    limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
    async with httpx.AsyncClient(timeout=120, headers={"User-Agent": UA}, limits=limits) as client:
        for sym in symbols:
            for y, m in months:
                meta = await download_month(client, sym, interval, y, m, force=force)
                out["months"].append({"symbol": sym, "year": y, "month": m, **meta})
                st = meta.get("status")
                if st in {"ready", "ready_no_official_checksum"}:
                    out["ok"] += 1
                elif st == "missing_remote":
                    out["missing"] += 1
                else:
                    out["fail"] += 1
    out["disk"] = disk_stats()
    return out


def iter_months(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    y, m = start
    ey, em = end
    out: list[tuple[int, int]] = []
    while (y, m) <= (ey, em):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def disk_stats() -> dict[str, Any]:
    ensure_dirs()
    import shutil

    usage = shutil.disk_usage(str(META_DIR))
    total_bytes = 0
    for p in META_DIR.parent.rglob("*"):
        if p.is_file():
            total_bytes += p.stat().st_size
    return {
        "history_bytes": total_bytes,
        "disk_free_bytes": usage.free,
        "disk_total_bytes": usage.total,
        "root": str(META_DIR.parent),
    }


def read_zip_rows(symbol: str, interval: str, year: int, month: int) -> list[dict[str, Any]]:
    path = raw_zip_path(symbol, interval, year, month)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return parse_klines_csv(extract_csv_from_zip(path))
