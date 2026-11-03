"""Prospective SHADOW_LIVE decision cycle — logs before outcomes; never real orders."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..indicators import sma
from ..ohlcv import fetch_klines
from .decisions import create_experiment, record_decision
from .execution import ExecutionAssumptions, estimate_fill_price
from .protocols import DEFAULT_SHADOW_LIVE_PROTOCOL, register_protocol
from .schema import ensure_prospect_schema


def _ensure_live_experiment(execute) -> tuple[int, int]:
    ensure_prospect_schema(execute)
    proto = register_protocol(execute, **{**DEFAULT_SHADOW_LIVE_PROTOCOL, "notes": "Etapa H"})
    existing = execute(
        """SELECT id FROM prospect_experiments
           WHERE experiment_type='SHADOW_LIVE' AND name=%s AND status='active'
           ORDER BY id DESC LIMIT 1""",
        ("shadow_live_sma10_50",),
    ).fetchone()
    if existing:
        return int(proto["id"]), int(existing["id"])
    exp_id = create_experiment(
        execute,
        experiment_type="SHADOW_LIVE",
        name="shadow_live_sma10_50",
        strategy="sma10_50_prospect",
        strategy_version="v1",
        protocol_id=int(proto["id"]),
        meta={"auto_activate": False, "paper_ai": False},
    )
    return int(proto["id"]), exp_id


async def run_shadow_live_cycle(
    db_factory,
    *,
    symbols: list[str] | None = None,
    breaker_active: bool = False,
    breaker_reason: str | None = None,
) -> dict[str, Any]:
    symbols = symbols or DEFAULT_SHADOW_LIVE_PROTOCOL["universe"]
    assumptions = ExecutionAssumptions()
    created = []

    with db_factory() as c:
        _, exp_id = _ensure_live_experiment(c.execute)
        runtime = c.execute("SELECT * FROM ml_runtime WHERE id=1").fetchone()
        paused = c.execute("SELECT paused FROM engine_state WHERE id=1").fetchone()

    system_state = {
        "mode": "PAPER_ONLY",
        "ml_mode": (runtime or {}).get("mode"),
        "engine_paused": bool(paused and paused.get("paused")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    risk_state = {
        "circuit_breaker_active": breaker_active,
        "circuit_breaker_reason": breaker_reason,
    }

    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": "ResearchPaperBot/prospect-live"}
    ) as client:
        for sym in symbols:
            try:
                payload = await fetch_klines(client, sym, "1h", limit=60, use_cache=True)
                candles = [c for c in payload["candles"] if c.get("is_closed")]
                if len(candles) < 55:
                    continue
                closes = [float(c["close"]) for c in candles]
                f = sma(closes, 10)
                s = sma(closes, 50)
                i = len(closes) - 1
                if f[i] is None or s[i] is None:
                    action, reason = "HOLD", "warmup"
                elif breaker_active:
                    action, reason = "HOLD", f"breaker_block:{breaker_reason}"
                elif f[i] > s[i]:  # type: ignore
                    action, reason = "BUY", "sma10_gt_sma50"
                else:
                    action, reason = "HOLD", "sma10_le_sma50"

                last = candles[-1]
                fill = estimate_fill_price(
                    side="BUY" if action == "BUY" else "SELL",
                    mid_or_ref=float(last["close"]),
                    assumptions=assumptions,
                    bar_volume=float(last["volume"]),
                    order_qty=None,
                    order_book=None,  # never invent book
                )
                with db_factory() as c:
                    # de-dupe same candle
                    exists = c.execute(
                        """SELECT id FROM prospect_decisions
                           WHERE experiment_id=%s AND symbol=%s AND candle_open_ms=%s""",
                        (exp_id, sym, last["open_time"]),
                    ).fetchone()
                    if exists:
                        created.append({"symbol": sym, "skipped": "duplicate_candle"})
                        continue
                    dec = record_decision(
                        c.execute,
                        experiment_id=exp_id,
                        symbol=sym,
                        interval="1h",
                        strategy="sma10_50_prospect",
                        strategy_version="v1",
                        action=action,
                        reason=reason,
                        horizon_bars=6,
                        observed_price=float(last["close"]),
                        data_ref={
                            "candle_open_ms": last["open_time"],
                            "source": "binance_public_klines",
                            "closed_only": True,
                        },
                        system_state=system_state,
                        risk_state=risk_state,
                        estimated_costs={
                            "fee_rate": assumptions.fee_rate,
                            "slip_rate": assumptions.base_slip_rate,
                            "spread_bps": assumptions.spread_bps,
                            "fill_preview": fill,
                        },
                        model_version=(runtime or {}).get("active_model_version"),
                        candle_open_ms=int(last["open_time"]),
                    )
                created.append(
                    {
                        "symbol": sym,
                        "action": action,
                        "decision_id": dec["id"],
                        "uid": str(dec["decision_uid"]),
                    }
                )
            except Exception as exc:
                created.append({"symbol": sym, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "experiment_id": exp_id,
        "experiment_type": "SHADOW_LIVE",
        "generated": len([x for x in created if "decision_id" in x]),
        "items": created,
        "note": "Decisions immutable; no paper SMA capital touched; no real orders.",
    }
