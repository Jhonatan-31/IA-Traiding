"""Periodic operational reconciliation — paper SMA + virtual research ledger.

Critical discrepancies raise alerts and can block new simulated BUY entries.
Never mutates decision payloads; never enables PAPER_AI or real orders.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from .degradation import THRESHOLDS, clear_alert, upsert_alert
from .ledger import accounting_identity_ok, ledger_snapshot

# Documented thresholds (Etapa J)
RECON_THRESHOLDS = {
    **THRESHOLDS,
    "price_mark_stale_s": 7200,  # marks older than 2h → warning
    "fill_vs_observed_bps_warn": 50,  # theoretical fill vs mid > 50 bps unusual for our model (~20bps slip+fee)
    "cash_identity_tol": Decimal("0.01"),
    "block_entries_on_critical": True,
}


def _d(x) -> Decimal:
    return Decimal(str(x))


def paper_sma_integrity(execute: Callable) -> dict[str, Any]:
    cash = _d(execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"])
    positions = list(execute("SELECT symbol, qty, cost FROM positions"))
    trades_n = int(execute("SELECT COUNT(*) AS n FROM trades").fetchone()["n"])
    invested = sum((_d(p["cost"]) for p in positions), Decimal("0"))
    issues = []
    if cash < 0:
        issues.append("negative_cash")
    if any(_d(p["qty"]) <= 0 for p in positions):
        issues.append("non_positive_qty")
    if any(_d(p["cost"]) < 0 for p in positions):
        issues.append("negative_position_cost")
    # Duplicate positions impossible with PK(symbol); check trade candle dupes heuristic
    trade_dupes = list(
        execute(
            """SELECT symbol, candle_ms, side, COUNT(*) AS n
               FROM trades GROUP BY 1,2,3 HAVING COUNT(*) > 1"""
        )
    )
    if trade_dupes:
        issues.append("duplicate_trades_same_candle")
    return {
        "ok": len(issues) == 0,
        "cash": float(cash),
        "invested_cost": float(invested),
        "equity_cost_basis": float(cash + invested),
        "positions": len(positions),
        "trades": trades_n,
        "issues": issues,
        "duplicate_trades": [dict(r) for r in trade_dupes],
    }


def market_data_freshness(execute: Callable) -> dict[str, Any]:
    row = execute("SELECT MAX(at) AS at, COUNT(*) AS n FROM prices").fetchone()
    at = row["at"] if row else None
    age = None
    if at is not None:
        if getattr(at, "tzinfo", None) is None:
            at = at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - at).total_seconds()
    status = "UNKNOWN"
    if age is None:
        status = "UNKNOWN"
    elif age > RECON_THRESHOLDS["price_mark_stale_s"]:
        status = "WARNING"
    else:
        status = "OK"
    return {
        "status": status,
        "prices_n": int(row["n"]) if row else 0,
        "prices_max_at": at.isoformat() if at else None,
        "age_s": age,
        "threshold_s": RECON_THRESHOLDS["price_mark_stale_s"],
    }


def prospect_decision_consistency(execute: Callable) -> dict[str, Any]:
    """Duplicates, fill vs observed, outcome/decision compatibility."""
    dupes = list(
        execute(
            """SELECT experiment_id, symbol, interval, candle_open_ms, COUNT(*) AS n
               FROM prospect_decisions
               WHERE candle_open_ms IS NOT NULL
               GROUP BY 1,2,3,4 HAVING COUNT(*) > 1"""
        )
    )
    rows = list(
        execute(
            """SELECT d.id, d.action, d.observed_price, d.estimated_costs_json,
                      d.resolution_status, o.status AS outcome_status,
                      o.observed_net_return, o.data_quality
               FROM prospect_decisions d
               LEFT JOIN prospect_outcomes o ON o.decision_id=d.id
               WHERE d.resolution_status <> 'PENDING' OR o.decision_id IS NOT NULL
               ORDER BY d.id DESC LIMIT 200"""
        )
    )
    fill_gaps = []
    incompat = []
    for r in rows:
        costs = r.get("estimated_costs_json") or {}
        if isinstance(costs, str):
            try:
                costs = json.loads(costs)
            except Exception:
                costs = {}
        fill = (costs.get("fill_preview") or {}).get("price")
        obs = r.get("observed_price")
        if fill is not None and obs is not None and float(obs) > 0:
            bps = abs(float(fill) - float(obs)) / float(obs) * 10_000
            if bps > RECON_THRESHOLDS["fill_vs_observed_bps_warn"] * 3:
                # only flag extreme outliers (model allows ~20bps); 150bps = critical-ish
                fill_gaps.append({"id": r["id"], "bps": round(bps, 2)})
        # Compatibility: RESOLVED decision must have outcome; statuses must match
        if r["resolution_status"] == "RESOLVED" and r.get("outcome_status") != "RESOLVED":
            incompat.append({"id": r["id"], "reason": "resolved_without_outcome"})
        if r["resolution_status"] == "INVALID" and r.get("outcome_status") not in (
            None,
            "INVALID",
        ):
            incompat.append({"id": r["id"], "reason": "invalid_status_mismatch"})
        if r["resolution_status"] == "PENDING" and r.get("outcome_status"):
            incompat.append({"id": r["id"], "reason": "pending_with_outcome"})

    pending = execute(
        """SELECT COUNT(*) AS n FROM prospect_decisions d
           JOIN prospect_experiments e ON e.id=d.experiment_id
           WHERE e.experiment_type='SHADOW_LIVE' AND d.resolution_status='PENDING'"""
    ).fetchone()["n"]

    return {
        "duplicate_decisions": [dict(x) for x in dupes],
        "duplicate_n": len(dupes),
        "fill_vs_observed_outliers": fill_gaps[:20],
        "prediction_outcome_incompat": incompat[:20],
        "pending_shadow_live": int(pending),
        "ok": len(dupes) == 0 and len(incompat) == 0,
    }


def horizon_audit(execute: Callable, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """For each PENDING SHADOW_LIVE decision: origin candle + exact horizon expiry (UTC)."""
    now = now or datetime.now(timezone.utc)
    rows = list(
        execute(
            """SELECT d.id, d.symbol, d.interval, d.action, d.candle_open_ms, d.horizon_bars,
                      d.created_at, d.decision_ts, d.observed_price, d.resolution_status
               FROM prospect_decisions d
               JOIN prospect_experiments e ON e.id=d.experiment_id
               WHERE e.experiment_type='SHADOW_LIVE' AND d.resolution_status='PENDING'
               ORDER BY d.id"""
        )
    )
    interval_ms = {"1h": 3_600_000, "5m": 300_000, "15m": 900_000, "4h": 14_400_000}
    out = []
    for r in rows:
        step = interval_ms.get(r["interval"] or "1h", 3_600_000)
        open_ms = r["candle_open_ms"]
        horizon = int(r["horizon_bars"])
        if open_ms is None:
            out.append({**dict(r), "horizon_ready": False, "reason": "missing_candle_open_ms"})
            continue
        exit_open_ms = int(open_ms) + horizon * step
        # Horizon complete when exit candle has closed → wall clock past exit_open + step
        ready_after_ms = exit_open_ms + step
        ready_at = datetime.fromtimestamp(ready_after_ms / 1000.0, tz=timezone.utc)
        exit_open_at = datetime.fromtimestamp(exit_open_ms / 1000.0, tz=timezone.utc)
        candle_open_at = datetime.fromtimestamp(int(open_ms) / 1000.0, tz=timezone.utc)
        ready = now >= ready_at
        out.append(
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "action": r["action"],
                "interval": r["interval"],
                "candle_open_ms": open_ms,
                "candle_open_utc": candle_open_at.isoformat(),
                "horizon_bars": horizon,
                "exit_open_utc": exit_open_at.isoformat(),
                "horizon_ready_after_utc": ready_at.isoformat(),
                "horizon_ready": ready,
                "seconds_until_ready": max(0, (ready_at - now).total_seconds()) if not ready else 0,
                "created_at": r["created_at"].isoformat()
                if hasattr(r["created_at"], "isoformat")
                else r["created_at"],
                "observed_price": r["observed_price"],
                "resolution_status": r["resolution_status"],
            }
        )
    return out


def run_reconciliation(execute: Callable) -> dict[str, Any]:
    """Full recon pass; opens/clears alerts; returns block_new_entries flag."""
    paper = paper_sma_integrity(execute)
    virt_id = accounting_identity_ok(execute)
    virt = ledger_snapshot(execute)
    market = market_data_freshness(execute)
    prospect = prospect_decision_consistency(execute)
    horizons = horizon_audit(execute)

    critical = []
    warnings = []
    if not paper["ok"]:
        critical.append({"code": "paper_sma_integrity", "issues": paper["issues"]})
    if not virt_id["ok"]:
        critical.append({"code": "virt_ledger_identity", "error": virt_id.get("error")})
    if prospect["duplicate_n"] > 0:
        critical.append({"code": "prospect_duplicates", "n": prospect["duplicate_n"]})
    if prospect["prediction_outcome_incompat"]:
        critical.append(
            {
                "code": "prediction_outcome_mismatch",
                "items": prospect["prediction_outcome_incompat"],
            }
        )
    if market["status"] == "WARNING":
        warnings.append({"code": "stale_market_data", "age_s": market["age_s"]})
    if market["status"] == "UNKNOWN":
        warnings.append({"code": "market_data_unknown"})

    # Alerts
    if critical:
        upsert_alert(
            execute,
            code="recon_critical",
            severity="ERROR",
            message=f"Reconciliación crítica: {[c['code'] for c in critical]}",
            evidence={"critical": critical, "thresholds": {k: str(v) for k, v in RECON_THRESHOLDS.items()}},
        )
    else:
        clear_alert(execute, "recon_critical")

    if warnings:
        upsert_alert(
            execute,
            code="recon_warning",
            severity="WARNING",
            message=f"Reconciliación con avisos: {[w['code'] for w in warnings]}",
            evidence={"warnings": warnings},
        )
    else:
        clear_alert(execute, "recon_warning")

    block = bool(critical) and RECON_THRESHOLDS["block_entries_on_critical"]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "paper_sma": paper,
        "virtual_ledger": {**virt, "identity": virt_id},
        "market_data": market,
        "prospect": prospect,
        "horizons_pending": horizons,
        "critical": critical,
        "warnings": warnings,
        "block_new_entries": block,
        "note": "Critical block only prevents new simulated BUY entries; never real orders.",
    }
