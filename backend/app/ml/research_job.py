"""Offline entrypoint: docker compose --profile ml run --rm ml-research"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .dataset import DEFAULT_SYMBOLS, build_dataset_incremental, load_jsonl
from .research import run_research
from .schema import ensure_ml_schema


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


async def run() -> dict:
    artifacts = Path(os.environ.get("ML_ARTIFACT_DIR", "/artifacts"))
    datasets = artifacts / "datasets"
    research_dir = artifacts / "research"
    interval = os.environ.get("ML_INTERVAL", "1h")
    max_bars = int(os.environ.get("ML_MAX_BARS", "1500"))
    symbols = os.environ.get("ML_SYMBOLS")
    symbol_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else DEFAULT_SYMBOLS[:15]
    )

    print("ML_RESEARCH start", flush=True)
    prior = None
    with db() as c:
        ensure_ml_schema(c.execute)
        row = c.execute(
            "SELECT data_path FROM ml_datasets ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row.get("data_path"):
            p = Path(row["data_path"])
            if p.exists():
                prior = p
            else:
                alt = datasets / p.name
                if alt.exists():
                    prior = alt

    meta = await build_dataset_incremental(
        symbols=symbol_list,
        interval=interval,
        max_bars=max_bars,
        out_dir=datasets,
        existing_path=prior,
    )
    print(
        "DATASET",
        meta.get("row_count"),
        meta.get("checksum"),
        meta.get("quality", {}).get("totals"),
        flush=True,
    )

    with db() as c:
        ensure_ml_schema(c.execute)
        c.execute(
            """INSERT INTO ml_datasets(interval, checksum, row_count, meta_json, data_path)
               VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(checksum) DO UPDATE SET meta_json=EXCLUDED.meta_json""",
            (
                interval,
                meta["checksum"],
                meta["row_count"],
                Jsonb(meta),
                meta.get("data_path"),
            ),
        )

    report = run_research(Path(meta["data_path"]), research_dir)
    print("RESEARCH", report.get("conclusion"), flush=True)
    print("ROBUST_EDGE", report.get("robust_edge_any"), flush=True)

    with db() as c:
        ensure_ml_schema(c.execute)
        c.execute(
            """INSERT INTO ml_experiments(name, params_json, metrics_json, notes)
               VALUES(%s,%s,%s,%s)""",
            (
                f"etapa_g_research_{report['created_at']}",
                Jsonb(
                    {
                        "symbols": symbol_list,
                        "max_bars": max_bars,
                        "execution": report.get("execution_model"),
                        "initial_capital": 1000,
                    }
                ),
                Jsonb(
                    {
                        "robust_edge_any": report.get("robust_edge_any"),
                        "best_selection": report.get("selection_window", {}).get(
                            "best_by_total_return"
                        ),
                        "holdout_preselected": report.get("final_holdout", {}).get(
                            "preselected_holdout"
                        ),
                        "conclusion": report.get("conclusion"),
                        "paper_ai_authorized": False,
                    }
                ),
                "Etapa G — no auto-activate; Shadow AI retained",
            ),
        )

    print("ML_RESEARCH done", report.get("artifact_path"), flush=True)
    return {"dataset": meta, "research": report}


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
