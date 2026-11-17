"""AN0 — auditoría reproducible del dataset AM (sin mutar evidencias)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .am_experiment import load_jsonl, subsample_by_bucket


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def audit_am_dataset(
    jsonl_path: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    events = load_jsonl(jsonl_path)
    manifest = {}
    if manifest_path and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    buckets = subsample_by_bucket(events, bucket_ms=30_000)
    by_sym: dict[str, list[int]] = {}
    for ev in events:
        sym = str(ev.get("symbol") or "").upper()
        ts = int(ev.get("received_at_ms") or 0)
        by_sym.setdefault(sym, []).append(ts)
    intervals = {}
    for sym, tss in by_sym.items():
        tss = sorted(tss)
        gaps = [tss[i + 1] - tss[i] for i in range(len(tss) - 1)]
        intervals[sym] = {
            "n": len(tss),
            "median_interval_ms": sorted(gaps)[len(gaps) // 2] if gaps else None,
            "mean_interval_ms": (sum(gaps) / len(gaps)) if gaps else None,
            "min_interval_ms": min(gaps) if gaps else None,
            "max_interval_ms": max(gaps) if gaps else None,
        }
    # REST AM typically lacked update_id
    n_with_u = sum(1 for e in events if e.get("update_id") is not None)
    return {
        "dataset": str(jsonl_path),
        "sha256": sha256_file(jsonl_path) if jsonl_path.exists() else None,
        "manifest": manifest,
        "n_events": len(events),
        "n_symbol_time_buckets_30s": len(buckets),
        "independence_clarification": {
            "reported_am_buckets": 60,
            "observed_buckets": len(buckets),
            "derived_rows_am": 360,
            "explanation": (
                "Buckets = unique (symbol, floor(ts/30s)). "
                "360 rows = 60 buckets × 2 sides × 3 sizes — DERIVED, temporally "
                "correlated within symbol and cross-sectionally across symbols."
            ),
            "independent_unit_for_stats": "symbol-time bucket (or coarser)",
            "naive_ci_on_360_invalid": True,
        },
        "intervals_ms": intervals,
        "n_with_update_id": n_with_u,
        "rest_bottleneck_hypothesis": (
            "Sequential REST poll ~2s + HTTP RTT explains ~3.8s mean spacing "
            f"(observed medians in intervals_ms). Not Binance WS push rate."
        ),
        "v1_v2_config_am": {
            "v1_default_slip": 0.001,
            "v1_spread_bps": 2.0,
            "v2_extra_slip": 0.0002,
            "fee_both": 0.001,
        },
        "evidence_preserved": True,
    }
