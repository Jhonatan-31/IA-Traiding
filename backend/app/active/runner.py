"""Strategy B runner — always loops; entries gated by persisted RUNNING status."""
from __future__ import annotations

import asyncio
import json
import os
import time

import psycopg
from psycopg.rows import dict_row

from . import POLICY_B_VERSION
from .engine import run_cycle
from .schema import ensure_active_schema


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


async def main() -> None:
    every = int(os.environ.get("ACTIVE_EVERY_SECONDS", "60"))
    print(
        f"ACTIVE_B_RUNNER start policy={POLICY_B_VERSION} every={every}s PAPER_ONLY",
        flush=True,
    )
    with db() as c:
        ensure_active_schema(c.execute)
        c.execute(
            """UPDATE active_state SET heartbeat_at=NOW(), policy_version=%s, updated_at=NOW()
               WHERE id=1""",
            (POLICY_B_VERSION,),
        )
    while True:
        t0 = time.time()
        try:
            summary = await run_cycle(db, every_seconds=every)
            print(f"ACTIVE_B_CYCLE {json.dumps(summary, default=str)[:500]}", flush=True)
        except Exception as exc:
            print(f"ACTIVE_B_ERROR {type(exc).__name__}: {exc}", flush=True)
            try:
                with db() as c:
                    c.execute(
                        """UPDATE active_state SET last_error=%s, updated_at=NOW() WHERE id=1""",
                        (f"{type(exc).__name__}: {str(exc)[:200]}",),
                    )
            except Exception:
                pass
        elapsed = time.time() - t0
        await asyncio.sleep(max(1.0, every - elapsed))


if __name__ == "__main__":
    asyncio.run(main())
