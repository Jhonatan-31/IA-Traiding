"""Pre-registered research protocols — hypothesis before looking at results."""
from __future__ import annotations

import json
from typing import Any, Callable


def register_protocol(
    execute: Callable,
    *,
    name: str,
    hypothesis: str,
    universe: list[str],
    period: dict,
    strategy: str,
    params: dict,
    costs: dict,
    success_criteria: str,
    abandon_criteria: str,
    notes: str | None = None,
) -> dict[str, Any]:
    row = execute(
        """INSERT INTO research_protocols(
            name, hypothesis, universe_json, period_json, strategy, params_json,
            costs_json, success_criteria, abandon_criteria, notes)
           VALUES(%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
           ON CONFLICT(name) DO UPDATE SET notes=EXCLUDED.notes
           RETURNING id, name, created_at, status""",
        (
            name,
            hypothesis,
            json.dumps(universe),
            json.dumps(period),
            strategy,
            json.dumps(params),
            json.dumps(costs),
            success_criteria,
            abandon_criteria,
            notes,
        ),
    ).fetchone()
    return dict(row)


def list_protocols(execute: Callable) -> list[dict]:
    return list(
        execute(
            "SELECT * FROM research_protocols ORDER BY id DESC LIMIT 50"
        )
    )


DEFAULT_SHADOW_LIVE_PROTOCOL = {
    "name": "etapa_h_shadow_live_default",
    "hypothesis": (
        "Prospective SHADOW_LIVE logging of strategy signals before outcomes are known "
        "does not by itself produce economic edge; used to measure calibration over time."
    ),
    "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"],
    "period": {"mode": "rolling_live", "horizon_bars": 6, "interval": "1h"},
    "strategy": "sma10_50_prospect",
    "params": {"fast": 10, "slow": 50, "auto_activate": False},
    "costs": {"fee_rate": 0.001, "slip_rate": 0.001, "spread_bps": 2.0},
    "success_criteria": (
        "After >=100 RESOLVED SHADOW_LIVE decisions, mean executable portfolio return "
        "exceeds cash with block-bootstrap CI lower bound > 0 on a pre-registered window."
    ),
    "abandon_criteria": (
        "If after 200 resolved decisions total_return <= cash and no robust edge, "
        "keep Shadow only; do not promote PAPER_AI."
    ),
}
