"""Immutable prospective decision logging."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from . import DECISION_ACTIONS, EXPERIMENT_KINDS


def create_experiment(
    execute: Callable,
    *,
    experiment_type: str,
    name: str,
    strategy: str,
    strategy_version: str = "v1",
    model_version: str | None = None,
    protocol_id: int | None = None,
    meta: dict | None = None,
) -> int:
    if experiment_type not in EXPERIMENT_KINDS:
        raise ValueError(f"invalid experiment_type {experiment_type}")
    row = execute(
        """INSERT INTO prospect_experiments(
            protocol_id, experiment_type, name, strategy, strategy_version, model_version, meta_json)
           VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)
           RETURNING id""",
        (
            protocol_id,
            experiment_type,
            name,
            strategy,
            strategy_version,
            model_version,
            json.dumps(meta or {}),
        ),
    ).fetchone()
    return int(row["id"])


def record_decision(
    execute: Callable,
    *,
    experiment_id: int,
    symbol: str,
    interval: str,
    strategy: str,
    strategy_version: str,
    action: str,
    reason: str,
    horizon_bars: int,
    observed_price: float | None,
    data_ref: dict,
    system_state: dict,
    risk_state: dict,
    estimated_costs: dict,
    model_version: str | None = None,
    candle_open_ms: int | None = None,
    decision_ts: datetime | None = None,
) -> dict[str, Any]:
    if action not in DECISION_ACTIONS:
        raise ValueError(f"invalid action {action}")
    uid = str(uuid.uuid4())
    ts = decision_ts or datetime.now(timezone.utc)
    row = execute(
        """INSERT INTO prospect_decisions(
            decision_uid, experiment_id, decision_ts, symbol, interval,
            strategy, strategy_version, model_version, data_ref_json,
            observed_price, action, reason, system_state_json, risk_state_json,
            estimated_costs_json, horizon_bars, candle_open_ms, resolution_status)
           VALUES(%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,'PENDING')
           RETURNING id, decision_uid, created_at, resolution_status""",
        (
            uid,
            experiment_id,
            ts,
            symbol.upper(),
            interval,
            strategy,
            strategy_version,
            model_version,
            json.dumps(data_ref),
            observed_price,
            action,
            reason,
            json.dumps(system_state),
            json.dumps(risk_state),
            json.dumps(estimated_costs),
            int(horizon_bars),
            candle_open_ms,
        ),
    ).fetchone()
    return dict(row)


def decision_counts(execute: Callable, experiment_type: str | None = None) -> dict[str, int]:
    if experiment_type:
        rows = list(
            execute(
                """SELECT d.resolution_status AS s, COUNT(*) AS n
                   FROM prospect_decisions d
                   JOIN prospect_experiments e ON e.id=d.experiment_id
                   WHERE e.experiment_type=%s
                   GROUP BY d.resolution_status""",
                (experiment_type,),
            )
        )
    else:
        rows = list(
            execute(
                """SELECT resolution_status AS s, COUNT(*) AS n
                   FROM prospect_decisions GROUP BY resolution_status"""
            )
        )
    out = {"PENDING": 0, "RESOLVED": 0, "INVALID": 0}
    for r in rows:
        out[str(r["s"])] = int(r["n"])
    out["total"] = sum(out.values())
    return out
