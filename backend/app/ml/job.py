"""Entrypoint for offline ml-train job."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .dataset import DEFAULT_SYMBOLS, build_dataset
from .schema import ensure_ml_schema
from .train import walk_forward_train


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


async def run() -> dict:
    artifacts = Path(os.environ.get("ML_ARTIFACT_DIR", "/artifacts"))
    datasets = artifacts / "datasets"
    models = artifacts / "models"
    interval = os.environ.get("ML_INTERVAL", "1h")
    max_bars = int(os.environ.get("ML_MAX_BARS", "1000"))
    symbols = os.environ.get("ML_SYMBOLS")
    symbol_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else DEFAULT_SYMBOLS[:15]
    )

    print("ML_TRAIN start", flush=True)
    meta = await build_dataset(
        symbols=symbol_list, interval=interval, max_bars=max_bars, out_dir=datasets
    )
    print("DATASET", meta.get("row_count"), meta.get("checksum"), flush=True)
    data_path = Path(meta["data_path"])
    result = walk_forward_train(data_path, models)
    print("TRAIN_STATUS", result.get("status"), result.get("model_version"), flush=True)

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
        if result.get("status") == "trained":
            status = (
                "validated_research"
                if result.get("validated_for_research")
                else "validation_insufficient"
            )
            c.execute(
                """INSERT INTO ml_models(version, algorithm, model_hash, artifact_path, metrics_json, status,
                      validated_for_research, validated_for_paper_ai, feature_names)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(version) DO UPDATE SET metrics_json=EXCLUDED.metrics_json""",
                (
                    result["model_version"],
                    result["algorithm"],
                    result["model_hash"],
                    result["model_path"],
                    Jsonb(result),
                    status,
                    bool(result.get("validated_for_research")),
                    False,
                    Jsonb(result["feature_names"]),
                ),
            )
            c.execute(
                """UPDATE ml_runtime SET active_model_version=%s, mode='SHADOW_AI',
                   updated_at=NOW(), notes=%s WHERE id=1""",
                (
                    result["model_version"],
                    "auto-set after offline train; execution still shadow-only",
                ),
            )
    summary_path = models / "last_train_summary.json"
    summary_path.write_text(json.dumps({"dataset": meta, "train": result}, indent=2), encoding="utf-8")
    print("ML_TRAIN done", summary_path, flush=True)
    return {"dataset": meta, "train": result}


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
