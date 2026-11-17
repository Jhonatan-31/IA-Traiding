"""CLI one-shot: captura AM autorizada + análisis. No autostart / no cron.

Usage (inside api container):
  python -m app.execution_v2.am_run_capture --seconds 600 --out /artifacts/history/etapa_am
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from .am_experiment import load_jsonl, run_analysis_on_capture, write_analysis
from .bbo_capture import am_authorized_plan, run_bounded_capture


async def main_async(seconds: float, out: Path, poll: float) -> dict:
    commit = os.environ.get("DEPLOY_GIT_COMMIT")
    plan = am_authorized_plan(max_seconds=seconds, poll_interval_s=poll, commit=commit)
    out.mkdir(parents=True, exist_ok=True)
    capture = await run_bounded_capture(plan, out_dir=out)
    analysis = None
    if capture.get("path") and Path(capture["path"]).exists():
        events = load_jsonl(Path(capture["path"]))
        analysis = run_analysis_on_capture(events, commit=commit)
        analysis_path = Path(capture["path"]).with_name(
            Path(capture["path"]).stem + "_analysis.json"
        )
        write_analysis(analysis_path, analysis)
        capture["analysis_path"] = str(analysis_path)
        capture["analysis_summary"] = {
            "n_comparable": analysis.get("n_comparable"),
            "n_rejected": analysis.get("n_rejected"),
            "meta": analysis.get("meta"),
            "by_size": analysis.get("by_size"),
            "spread_abs_distribution": analysis.get("spread_abs_distribution"),
            "price_diff_v2_minus_v1": analysis.get("price_diff_v2_minus_v1"),
        }
    summary_path = out / "last_experiment.json"
    summary_path.write_text(json.dumps(capture, indent=2, ensure_ascii=False), encoding="utf-8")
    capture["summary_path"] = str(summary_path)
    return capture


def main() -> None:
    p = argparse.ArgumentParser(description="AM bounded BBO capture (one-shot)")
    p.add_argument("--seconds", type=float, default=600.0, help="max duration (clamped to 1800)")
    p.add_argument("--poll", type=float, default=2.0, help="poll interval seconds")
    p.add_argument(
        "--out",
        type=str,
        default="/artifacts/history/etapa_am",
        help="output directory",
    )
    args = p.parse_args()
    result = asyncio.run(main_async(args.seconds, Path(args.out), args.poll))
    print(json.dumps({"ok": result.get("ok"), "stop_reason": result.get("stop_reason"),
                      "n_events": result.get("n_events"),
                      "path": result.get("path"),
                      "analysis_path": result.get("analysis_path"),
                      "summary_path": result.get("summary_path")}, indent=2))


if __name__ == "__main__":
    main()
