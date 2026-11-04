"""Read-only audit: per-decision horizon candle availability (no resolve writes)."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from app.main import db
from app.ml.resolve import expected_exit_open_ms
from app.ohlcv import fetch_klines
from app.prospect.schema import ensure_prospect_schema
from app.prospect.reconcile import horizon_audit

async def main() -> None:
    now = datetime.now(timezone.utc)
    print(f"now_utc={now.isoformat()}")
    with db() as c:
        ensure_prospect_schema(c.execute)
        ha = horizon_audit(c.execute)
        print("horizon_audit_n", len(ha), "any_ready", any(h.get("horizon_ready") for h in ha))
        for h in ha:
            print(
                "CLOCK", h["id"], h["symbol"], h["action"] if "action" in h else "",
                "open", h.get("candle_open_utc"),
                "ready_after", h.get("horizon_ready_after_utc"),
                "ready?", h.get("horizon_ready"),
                "sec_until", h.get("seconds_until_ready"),
            )
        rows = list(c.execute(
            """SELECT d.id, d.symbol, d.action, d.interval, d.horizon_bars, d.candle_open_ms, d.resolution_status
               FROM prospect_decisions d JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE' AND d.candle_open_ms BETWEEN 1793728800000 AND 1793746800000
               ORDER BY d.candle_open_ms, d.symbol"""
        ))
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": "ResearchPaperBot/horizon-audit"}) as client:
        cache = {}
        print("---CANDLE_CHECK---")
        for r in rows:
            sym = r["symbol"]
            interval = r["interval"] or "1h"
            h = int(r["horizon_bars"])
            cms = int(r["candle_open_ms"])
            exit_open = expected_exit_open_ms(cms, interval, h)
            ready_clock = cms + (h + 1) * 3600000
            clock_ok = int(now.timestamp() * 1000) >= ready_clock
            if sym not in cache:
                payload = await fetch_klines(client, sym, interval, limit=48, use_cache=False)
                cache[sym] = {int(c["open_time"]): c for c in payload["candles"] if c.get("is_closed", True)}
            by = cache[sym]
            has_exit = exit_open in by
            last = max(by) if by else 0
            horizon_ok = last >= exit_open and has_exit
            if not clock_ok:
                reason = "clock_before_ready_after_close"
            elif not has_exit:
                reason = "missing_exit_closed_candle"
            elif not horizon_ok:
                reason = "horizon_incomplete"
            else:
                reason = "ok_ready_to_resolve"
            print(f"{r['id']}\t{sym}\t{r['action']}\tclock_ok={clock_ok}\thas_exit={has_exit}\thorizon_ok={horizon_ok}\t{r['resolution_status']}\t{reason}")

asyncio.run(main())
