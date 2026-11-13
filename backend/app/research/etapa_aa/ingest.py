"""AA2 — ingesta controlada 1d post-2025-10 desde Binance Vision."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..history.coverage import summarize_symbol
from ..history.download import UA, download_month, disk_stats, iter_months
from ..history.paths import ensure_dirs
from ..history.store import list_partitions, write_month_parquet
from ..history.download import read_zip_rows
from . import EVAL_END_EXCLUSIVE, EVAL_START, SYMBOLS


def months_aa() -> list[tuple[int, int]]:
    return iter_months((2025, 11), (2026, 10))


def independence_audit() -> dict[str, Any]:
    """Clasifica independencia sin mirar retornos del período nuevo."""
    post = []
    for s in SYMBOLS:
        for p in list_partitions(s, "1d"):
            y, m = int(p["year"]), int(p["month"])
            if (y, m) >= (2025, 11):
                post.append(f"{s}-{y}-{m:02d}")
    # Uso previo en investigación: span Z terminó 2025-10-31; D28H5 elegido en OOS interno Z
    used_for_selection = False
    previously_ingested = len(post) > 0
    if not previously_ingested and not used_for_selection:
        label = "evaluacion_temporal_nueva_previa_no_utilizada"
    elif previously_ingested and not used_for_selection:
        label = "evaluacion_temporal_nueva_independencia_parcial"
    else:
        label = "evaluacion_adicional_no_independiente"
    return {
        "label": label,
        "previously_ingested_post_oct2025_1d": post,
        "used_to_select_d28h5": used_for_selection,
        "evidence": [
            "Etapa Z span documentado 2024-11→2025-10",
            "D28H5 seleccionada por OOS interno dentro de ese span",
            "Prerregistro AA escrito antes de descargar/evaluar retornos nuevos",
        ],
        "caveat": "Conocer que existiría un período futuro no equivale a haber visto sus retornos",
    }


async def ingest_aa_1d(*, force: bool = False) -> dict[str, Any]:
    ensure_dirs()
    disk = disk_stats()
    results = []
    async with httpx.AsyncClient(timeout=120, headers={"User-Agent": UA}) as client:
        for symbol in SYMBOLS:
            for y, m in months_aa():
                dl = await download_month(client, symbol, "1d", y, m, force=force)
                item: dict[str, Any] = {
                    "symbol": symbol,
                    "year": y,
                    "month": m,
                    "download": {k: dl.get(k) for k in ("status", "bytes", "sha256", "checksum_match", "source")},
                    "ingested": False,
                }
                if dl.get("status") in {"ready", "ready_no_official_checksum"}:
                    rows = read_zip_rows(symbol, "1d", y, m)
                    meta = write_month_parquet(
                        symbol,
                        "1d",
                        y,
                        m,
                        rows,
                        interval_ms=24 * 60 * 60_000,
                        source_meta={**dl, "etapa": "AA"},
                    )
                    item["ingested"] = True
                    item["n_bars"] = meta.get("n_bars")
                    item["validation_ok"] = (meta.get("validation") or {}).get("ok")
                results.append(item)
    cov = {s: summarize_symbol(s, "1d") for s in SYMBOLS}
    ok_n = sum(1 for r in results if r.get("ingested"))
    return {
        "ok": ok_n == len(SYMBOLS) * len(months_aa()),
        "ingested_months": ok_n,
        "expected_months": len(SYMBOLS) * len(months_aa()),
        "disk": disk,
        "independence": independence_audit(),
        "coverage_1d": {
            s: {
                "n_bars": c.get("n_bars"),
                "first_iso": c.get("first_iso"),
                "last_iso": c.get("last_iso"),
                "gap_count": c.get("gap_count"),
                "verified": c.get("verified"),
            }
            for s, c in cov.items()
        },
        "period_candidate": {
            "start": EVAL_START.isoformat(),
            "end_exclusive": EVAL_END_EXCLUSIVE.isoformat(),
        },
        "details": results,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }


def run_ingest_aa(force: bool = False) -> dict[str, Any]:
    return asyncio.run(ingest_aa_1d(force=force))
