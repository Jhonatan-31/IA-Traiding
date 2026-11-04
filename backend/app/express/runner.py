"""Express runner — absolute end 2026-11-04T01:00:00Z. PAPER_ONLY."""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from .engine import run_cycle
from .policy import END_UTC, POLICY_VERSION, is_ended, seconds_remaining
from .schema import ensure_express_schema


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


async def main() -> None:
    every = int(os.environ.get("EXPRESS_EVERY_SECONDS", "60"))
    print(
        f"EXPRESS_RUNNER start policy={POLICY_VERSION} end={END_UTC.isoformat()} every={every}s PAPER_ONLY",
        flush=True,
    )
    with db() as c:
        ensure_express_schema(c.execute)
        c.execute(
            """UPDATE express_state SET status='RUNNING', started_at=COALESCE(started_at,NOW()),
                 heartbeat_at=NOW(), policy_version=%s, updated_at=NOW() WHERE id=1""",
            (POLICY_VERSION,),
        )
    while True:
        if is_ended():
            with db() as c:
                ensure_express_schema(c.execute)
                c.execute(
                    """UPDATE express_state SET status='ENDED', ended_at=COALESCE(ended_at,NOW()),
                         heartbeat_at=NOW(), updated_at=NOW(),
                         meta_json=meta_json || %s::jsonb WHERE id=1""",
                    (json.dumps({"end_reason": "absolute_deadline", "ended_loop": True}),),
                )
            print(
                f"EXPRESS_ENDED at={datetime.now(timezone.utc).isoformat()} remaining=0 — no retroactive ops",
                flush=True,
            )
            break
        try:
            summary = await run_cycle(db)
            print(
                "EXPRESS_CYCLE "
                + json.dumps(
                    {
                        "at": summary.get("at"),
                        "sec_left": round(seconds_remaining(), 1),
                        "decisions": len(summary.get("decisions") or []),
                        "fills": len(summary.get("fills") or []),
                        "rejects": len(summary.get("rejects") or []),
                        "ended": summary.get("ended"),
                        "status": summary.get("status"),
                    }
                ),
                flush=True,
            )
            if summary.get("status") == "ENDED":
                break
        except Exception as exc:
            print(f"EXPRESS_ERROR {type(exc).__name__}: {exc}", flush=True)
            try:
                with db() as c:
                    c.execute(
                        """UPDATE express_state SET last_error=%s, heartbeat_at=NOW(), updated_at=NOW()
                           WHERE id=1""",
                        (f"{type(exc).__name__}: {exc}"[:500],),
                    )
            except Exception:
                pass
        # Sleep but wake near deadline
        left = seconds_remaining()
        if left <= 0:
            continue
        time.sleep(min(every, max(1, left)))


if __name__ == "__main__":
    asyncio.run(main())
