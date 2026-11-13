"""AB0 — auditoría de validez de artefactos Z/AA."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..etapa_aa.freeze import verify_freeze
from ..etapa_aa.run_aa import reconcile_z_oos
from . import AA_COMMIT, AA_HOLDOUT_CONSUMED, EXPECTED_CONFIG_HASH, TARGET_ID


def _load(*cands: str) -> dict[str, Any] | None:
    for c in cands:
        p = Path(c)
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def audit_validity() -> dict[str, Any]:
    freeze = verify_freeze()
    aa = _load(
        "/artifacts/history/etapa_aa_results.json",
        "data/market_history/etapa_aa_results.json",
    )
    z = _load(
        "/artifacts/history/etapa_z_results.json",
        "data/market_history/etapa_z_results.json",
    )
    recon = reconcile_z_oos()
    primary = ((aa or {}).get("evaluation") or {}).get("primary") or {}
    checks = {
        "hash_match": freeze.get("hash_match") is True and freeze.get("config_hash") == EXPECTED_CONFIG_HASH,
        "target": TARGET_ID,
        "z_recon_ok": recon.get("ok") is True,
        "z_recon_net": recon.get("reproduced_net"),
        "aa_d28_net": primary.get("d28h5_net"),
        "aa_bh_eq_net": primary.get("bh_eq_net"),
        "aa_excess": primary.get("excess_net"),
        "aa_costs": primary.get("d28h5_costs"),
        "aa_artifact": aa is not None,
        "z_artifact": z is not None,
        "holdout_aa_consumed": AA_HOLDOUT_CONSUMED,
        "aa_period_note": "2025-11→2026-10 consumido como holdout AA; AB no lo reutiliza como prueba independiente",
        "min_hold_not_in_code": freeze.get("executable_behavior", {}).get("min_hold_in_code") is False,
    }
    # tolerancias vs números reportados
    def near(a, b, tol=1.0):
        return a is not None and b is not None and abs(float(a) - float(b)) <= tol

    checks["match_reported_z_340"] = near(recon.get("reproduced_net"), 340.5377, 1.0)
    checks["match_reported_aa_d28"] = near(primary.get("d28h5_net"), -126.42, 1.0)
    checks["match_reported_aa_eq"] = near(primary.get("bh_eq_net"), -398.32, 1.0)
    checks["match_reported_excess"] = near(primary.get("excess_net"), 271.90, 1.0)
    checks["match_reported_costs"] = near(primary.get("d28h5_costs"), 72.73, 1.0)

    ok = (
        checks["hash_match"]
        and checks["z_recon_ok"]
        and checks["aa_artifact"]
        and checks["match_reported_aa_d28"]
    )
    return {
        "ok": ok,
        "freeze": freeze,
        "checks": checks,
        "aa_commit_expected": AA_COMMIT,
        "d28h5_rules": freeze.get("executable_behavior"),
        "costs_frozen": freeze.get("costs"),
    }
