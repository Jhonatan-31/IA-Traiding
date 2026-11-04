"""DEMO runner — always loops; entries gated by persisted RUNNING status."""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from . import POLICY_VERSION
from .engine import run_cycle
from .schema import ensure_demo_schema


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


async def main() -> None:
    every = int(os.environ.get("DEMO_EVERY_SECONDS", "60"))
    print(
        f"DEMO_RUNNER start policy={POLICY_VERSION} every={every}s PAPER_ONLY (entries only if RUNNING)",
        flush=True,
    )
    with db() as c:
        ensure_demo_schema(c.execute)
        c.execute(
            """UPDATE demo_state SET heartbeat_at=NOW(), policy_version=%s, updated_at=NOW()
               WHERE id=1""",
            (POLICY_VERSION,),
        )
    while True:
        try:
            with db() as c:
                st = c.execute("SELECT status FROM demo_state WHERE id=1").fetchone()
            status = (st or {}).get("status") or "STOPPED"
            summary = await run_cycle(db, every_seconds=every)
            print(
                "DEMO_CYCLE "
                + json.dumps(
                    {
                        "at": summary.get("at"),
                        "bot_status": summary.get("bot_status") or status,
                        "allow_entries": summary.get("allow_entries"),
                        "decisions": len(summary.get("decisions") or []),
                        "fills": len(summary.get("fills") or []),
                        "rejects": len(summary.get("rejects") or []),
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            print(f"DEMO_ERROR {type(exc).__name__}: {exc}", flush=True)
            try:
                with db() as c:
                    c.execute(
                        """UPDATE demo_state SET last_error=%s, heartbeat_at=NOW(), updated_at=NOW()
                           WHERE id=1""",
                        (f"{type(exc).__name__}: {exc}"[:500],),
                    )
            except Exception:
                pass
        time.sleep(every)


if __name__ == "__main__":
    asyncio.run(main())
