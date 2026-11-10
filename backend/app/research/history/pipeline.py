"""Orquestación: smoke → expand → aggregate → metadatos PG."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable

from .aggregate import INTERVAL_MS, aggregate_bars
from .coverage import full_coverage_report, summarize_symbol
from .download import disk_stats, download_month, download_range, iter_months, read_zip_rows
from .paths import ensure_dirs
from .schema import ensure_history_schema, upsert_coverage, upsert_file_meta
from .store import list_partitions, write_month_parquet


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
HIGHER_TF = ["5m", "15m", "1h", "4h", "1d"]


async def ingest_month(
    symbol: str,
    year: int,
    month: int,
    *,
    force: bool = False,
    execute: Callable | None = None,
) -> dict[str, Any]:
    import httpx
    from .download import UA

    ensure_dirs()
    async with httpx.AsyncClient(timeout=120, headers={"User-Agent": UA}) as client:
        dl = await download_month(client, symbol, "1m", year, month, force=force)
    if dl.get("status") not in {"ready", "ready_no_official_checksum"}:
        return {"symbol": symbol, "year": year, "month": month, "download": dl, "ingested": False}
    rows = read_zip_rows(symbol, "1m", year, month)
    meta = write_month_parquet(symbol, "1m", year, month, rows, source_meta=dl)
    # higher TFs for this month
    tf_meta = {}
    for iv in HIGHER_TF:
        agg = aggregate_bars(rows, iv)
        if agg:
            tf_meta[iv] = write_month_parquet(
                symbol, iv, year, month, agg, interval_ms=INTERVAL_MS[iv], source_meta={"from": "1m_aggregate"}
            )
    if execute is not None:
        upsert_file_meta(execute, meta)
        for iv, m in tf_meta.items():
            upsert_file_meta(execute, m)
        cov = summarize_symbol(symbol, "1m")
        upsert_coverage(
            execute,
            {
                "symbol": symbol,
                "interval": "1m",
                "first_open_time": cov.get("first_open_time"),
                "last_open_time": cov.get("last_open_time"),
                "n_bars": cov.get("n_bars"),
                "gap_count": cov.get("gap_count"),
                "missing_bars_est": cov.get("missing_bars_est"),
                "coverage_pct": cov.get("coverage_pct"),
                "source": "binance_vision",
            },
        )
    return {
        "symbol": symbol,
        "year": year,
        "month": month,
        "download": {k: dl.get(k) for k in ("status", "bytes", "sha256", "checksum_match", "source")},
        "parquet": {"n_bars": meta.get("n_bars"), "validation_ok": (meta.get("validation") or {}).get("ok")},
        "higher_tf": {k: v.get("n_bars") for k, v in tf_meta.items()},
        "ingested": True,
    }


async def run_smoke(execute: Callable | None = None) -> dict[str, Any]:
    """Valida tubería con 1 mes / 1 símbolo (BTCUSDT mes reciente disponible)."""
    # Octubre 2025 — verificado disponible en Binance Vision al inicio de Etapa W
    r = await ingest_month("BTCUSDT", 2025, 10, execute=execute)
    return {
        "etapa": "W",
        "mode": "smoke",
        "paper_only": True,
        "result": r,
        "disk": disk_stats(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_expand(
    *,
    start: tuple[int, int] = (2024, 11),
    end: tuple[int, int] = (2025, 10),
    symbols: list[str] | None = None,
    execute: Callable | None = None,
) -> dict[str, Any]:
    """Amplía cobertura ~12 meses sin seleccionar períodos favorables ad hoc.

    Ventana fija: 2024-11 → 2025-10 (12 meses calendarios).
    """
    symbols = symbols or SYMBOLS
    months = iter_months(start, end)
    results = []
    for sym in symbols:
        for y, m in months:
            results.append(await ingest_month(sym, y, m, execute=execute))
    cov = full_coverage_report(symbols)
    return {
        "etapa": "W",
        "mode": "expand_12m",
        "paper_only": True,
        "window": {"start": f"{start[0]:04d}-{start[1]:02d}", "end": f"{end[0]:04d}-{end[1]:02d}"},
        "symbols": symbols,
        "n_jobs": len(results),
        "ingested_ok": sum(1 for r in results if r.get("ingested")),
        "failed": [r for r in results if not r.get("ingested")],
        "coverage": cov,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def sync_coverage_to_db(execute: Callable, symbols: list[str] | None = None) -> dict[str, Any]:
    ensure_history_schema(execute)
    symbols = symbols or SYMBOLS
    out = []
    for s in symbols:
        for iv in ["1m", *HIGHER_TF]:
            cov = summarize_symbol(s, iv)
            if not cov.get("available"):
                continue
            upsert_coverage(
                execute,
                {
                    "symbol": s,
                    "interval": iv,
                    "first_open_time": cov.get("first_open_time"),
                    "last_open_time": cov.get("last_open_time"),
                    "n_bars": cov.get("n_bars"),
                    "gap_count": cov.get("gap_count"),
                    "missing_bars_est": cov.get("missing_bars_est"),
                    "coverage_pct": cov.get("coverage_pct"),
                    "source": "binance_vision",
                },
            )
            out.append({"symbol": s, "interval": iv, "n_bars": cov.get("n_bars")})
    return {"upserted": out}


def main() -> None:
    p = argparse.ArgumentParser(description="Etapa W market history pipeline")
    p.add_argument("--mode", choices=["smoke", "expand"], default="smoke")
    p.add_argument("--start", default="2024-11")
    p.add_argument("--end", default="2025-10")
    args = p.parse_args()

    def _parse(ym: str) -> tuple[int, int]:
        y, m = ym.split("-")
        return int(y), int(m)

    if args.mode == "smoke":
        print(json.dumps(asyncio.run(run_smoke()), indent=2, default=str))
    else:
        print(
            json.dumps(
                asyncio.run(run_expand(start=_parse(args.start), end=_parse(args.end))),
                indent=2,
                default=str,
            )
        )


if __name__ == "__main__":
    main()
