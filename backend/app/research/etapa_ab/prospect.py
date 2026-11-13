"""AB6/AB7 — observación prospectiva (preparada, desactivada por defecto).

No ejecutor. No ledger operativo. No altera A/B.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import EXPECTED_CONFIG_HASH, TARGET_ID

PROTOCOL_VERSION = "AB-PROSPECT-v1"
DEFAULT_HORIZON_DAYS = 90
# Observación NO arranca automáticamente: requiere flag explícito en futuro.
OBSERVATION_ENABLED = False


def frozen_protocol() -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "strategy": TARGET_ID,
        "config_hash": EXPECTED_CONFIG_HASH,
        "primary_benchmark": "FIXED-55-EQ",
        "secondary_benchmarks": ["CASH", "Z-BH-EQ", "VOL-SCALE-EQ"],
        "primary_metric": "excess_net_vs_FIXED_55_EQ",
        "secondary_metrics": [
            "max_drawdown",
            "avg_exposure",
            "fees_and_frictions",
            "turnover_events",
            "cash_days",
        ],
        "costs": {"fee": 0.001, "slip": 0.0005, "spread_bps": 1.0},
        "horizon_calendar_days": DEFAULT_HORIZON_DAYS,
        "min_coverage_pct": 95.0,
        "min_effective_sample_days": 60,
        "max_acceptable_dd": 0.35,
        "stop_conditions": [
            "cobertura < 95% sostenida >7d",
            "hash o código D28H5 diverge",
            "detección de look-ahead o corrupción de datos",
        ],
        "reject_if": [
            "exceso neto vs FIXED-55 ≤ 0 al horizonte con cobertura OK",
            "DD > 35% con exposición media > 80%",
        ],
        "interim_label": "descriptivo — no prueba independiente",
        "aa_holdout_reuse_forbidden": True,
        "observation_is_not_trading": True,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


def observation_status(store_dir: str | Path | None = None) -> dict[str, Any]:
    proto = frozen_protocol()
    root = Path(store_dir or "/artifacts/history/prospect_ab")
    decisions = root / "decisions.jsonl"
    n = 0
    last = None
    if decisions.is_file():
        lines = [ln for ln in decisions.read_text(encoding="utf-8").splitlines() if ln.strip()]
        n = len(lines)
        if lines:
            try:
                last = json.loads(lines[-1])
            except Exception:
                last = {"raw": lines[-1][:200]}
    return {
        "enabled": OBSERVATION_ENABLED,
        "status": "PREPARED_DISABLED" if not OBSERVATION_ENABLED else "ACTIVE",
        "reason_disabled": (
            "No se fuerza arranque para no competir con runners/lab existentes; "
            "protocolo congelado listo para activación explícita futura."
        ),
        "protocol": proto,
        "start_at": None,
        "decisions_recorded": n,
        "last_signal": last,
        "coverage": None,
        "errors": [],
        "limitations": [
            "Sin BBO",
            "Host suspendido no instrumentado aún",
            "Requiere job de investigación separado sin tocar ledgers",
        ],
    }


def decision_schema() -> dict[str, Any]:
    return {
        "required_fields": [
            "timestamp_utc",
            "symbol_universe",
            "version",
            "config_hash",
            "data_asof",
            "indicators",
            "signal",
            "strategy_state",
            "target_weights",
            "ref_prices",
            "hypothetical_costs",
            "reason",
            "data_quality",
        ],
        "immutable_after_write": True,
        "outcomes_separate_file": "outcomes.jsonl",
    }
