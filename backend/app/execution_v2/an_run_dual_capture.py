"""CLI one-shot AN: REST + WebSocket bookTicker en paralelo (acotado).

  python -m app.execution_v2.an_run_dual_capture --seconds 180 --out /artifacts/history/etapa_an
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from .am_experiment import load_jsonl
from .bbo_capture import CapturePlan, run_bounded_capture
from .bbo_ws_capture import WsCapturePlan, run_ws_book_ticker_capture
from .fair_compare import run_fair_analysis


async def dual(seconds: float, out: Path, poll: float) -> dict:
    commit = os.environ.get("DEPLOY_GIT_COMMIT")
    out.mkdir(parents=True, exist_ok=True)
    rest_plan = CapturePlan(
        max_seconds=seconds,
        poll_interval_s=poll,
        max_events=min(30_000, int(seconds / max(poll, 0.1)) * 3 + 10),
        max_bytes=12 * 1024 * 1024,
        experiment_id=f"AN-REST-{int(asyncio.get_event_loop().time())}",
        commit=commit,
        authorized=True,
    )
    ws_plan = WsCapturePlan(
        max_seconds=seconds,
        max_events=20_000,
        max_bytes=12 * 1024 * 1024,
        experiment_id=f"AN-WS-{int(asyncio.get_event_loop().time())}",
        commit=commit,
    )
    rest_task = asyncio.create_task(run_bounded_capture(rest_plan, out_dir=out / "rest"))
    ws_task = asyncio.create_task(run_ws_book_ticker_capture(ws_plan, out_dir=out / "ws"))
    rest, ws = await asyncio.gather(rest_task, ws_task)

    fair_rest = fair_ws = None
    if rest.get("path") and Path(rest["path"]).exists():
        fair_rest = run_fair_analysis(load_jsonl(Path(rest["path"])))
        (out / "fair_rest.json").write_text(
            json.dumps(fair_rest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    if ws.get("path") and Path(ws["path"]).exists():
        fair_ws = run_fair_analysis(load_jsonl(Path(ws["path"])))
        (out / "fair_ws.json").write_text(
            json.dumps(fair_ws, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    summary = {
        "ok": bool(rest.get("ok") or ws.get("ok")),
        "seconds": seconds,
        "commit": commit,
        "rest": {
            "ok": rest.get("ok"),
            "n_events": rest.get("n_events"),
            "bytes": rest.get("bytes_written"),
            "stop": rest.get("stop_reason"),
            "path": rest.get("path"),
            "duration_ms": (rest.get("ended_at_ms") or 0) - (rest.get("started_at_ms") or 0),
        },
        "ws": {
            "ok": ws.get("ok"),
            "n_events": ws.get("n_events"),
            "bytes": ws.get("bytes_written"),
            "stop": ws.get("stop_reason"),
            "path": ws.get("path"),
            "reconnects": ws.get("n_reconnects"),
            "msg_rate": (ws.get("manifest") or {}).get("msg_rate_per_s"),
            "duration_ms": (ws.get("ended_at_ms") or 0) - (ws.get("started_at_ms") or 0),
        },
        "comparison_note": (
            "More WS messages ≠ more accurate fills; measures continuity of top-of-book updates."
        ),
        "fair_rest_summary": _fair_brief(fair_rest) if fair_rest else None,
        "fair_ws_summary": _fair_brief(fair_ws) if fair_ws else None,
        "permanent_service": False,
    }
    (out / "last_dual_experiment.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def _fair_brief(fair: dict) -> dict:
    return {
        "independence": fair.get("independence"),
        "legacy_n": (fair.get("legacy") or {}).get("n_comparable"),
        "matched_n": (fair.get("matched") or {}).get("n_comparable"),
        "legacy_by_symbol_side_keys": list(
            ((fair.get("legacy") or {}).get("by_symbol_side") or {}).keys()
        ),
        "matched_notional_weighted": (fair.get("matched") or {}).get("notional_weighted"),
        "legacy_notional_weighted": (fair.get("legacy") or {}).get("notional_weighted"),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seconds", type=float, default=180.0)
    p.add_argument("--poll", type=float, default=2.0)
    p.add_argument("--out", type=str, default="/artifacts/history/etapa_an")
    args = p.parse_args()
    # Clamp to AN5
    seconds = min(float(args.seconds), 600.0)
    out = asyncio.run(dual(seconds, Path(args.out), args.poll))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
