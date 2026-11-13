"""AA0 — verificación de congelación e identidad con Etapa Z."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..etapa_z import FEE_RATE, INITIAL_CAPITAL, SLIP_RATE, SPREAD_BPS
from ..etapa_z.hypotheses import HYPOTHESES
from ..etapa_z.run_z import _config_hash
from . import EXPECTED_CONFIG_HASH, TARGET_ID, Z_COMMIT


def verify_freeze() -> dict[str, Any]:
    h = _config_hash()
    meta = HYPOTHESES.get(TARGET_ID) or {}
    executable = {
        "weight_builder": "make_tsmom(28)",
        "lookback": 28,
        "daily_reeval": True,
        "min_hold_in_code": False,
        "min_hold_in_meta": (meta.get("params") or {}).get("min_hold"),
        "note": "params.min_hold=5 NO se aplica en código; evaluación usa make_tsmom(28) diario",
    }
    ok = h == EXPECTED_CONFIG_HASH and TARGET_ID in HYPOTHESES
    return {
        "ok": ok,
        "config_hash": h,
        "expected_hash": EXPECTED_CONFIG_HASH,
        "hash_match": h == EXPECTED_CONFIG_HASH,
        "target": TARGET_ID,
        "z_commit_expected": Z_COMMIT,
        "costs": {
            "fee": FEE_RATE,
            "slip": SLIP_RATE,
            "spread_bps": SPREAD_BPS,
            "capital": INITIAL_CAPITAL,
        },
        "rules_meta": {
            k: meta.get(k)
            for k in ("tf", "universe", "entry", "exit", "abstain", "params", "frozen")
        },
        "executable_behavior": executable,
        "benchmark_primary": "Z-BH-EQ",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "blocking": [] if ok else ["hash_or_target_mismatch"],
    }


def manifest_digest(freeze: dict[str, Any]) -> str:
    blob = json.dumps(
        {
            "hash": freeze.get("config_hash"),
            "target": TARGET_ID,
            "executable": freeze.get("executable_behavior"),
            "costs": freeze.get("costs"),
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
