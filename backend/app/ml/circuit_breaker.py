"""Circuit breaker for simulated new entries — never auto-closes positions."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable


DEFAULT_LIMITS = {
    "max_daily_loss_pct": 5.0,
    "max_drawdown_pct": 15.0,
    "max_data_age_s": 7200,
    "max_binance_errors": 5,
    "max_missing_marks": 2,
    "max_gross_exposure_pct": 80.0,
}


def evaluate_circuit_breaker(
    *,
    equity: float | None,
    initial_capital: float,
    equity_series: list[float],
    day_start_equity: float | None,
    data_age_s: float | None,
    recent_binance_errors: int,
    missing_marks: int,
    invested_cost: float,
    cash: float,
    critical_down: bool,
    limits: dict[str, Any] | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    Returns (should_block_new_entries, reason, evidence).
    Does not recommend closing existing positions.
    """
    lim = {**DEFAULT_LIMITS, **(limits or {})}
    evidence: dict[str, Any] = {"checked_at": datetime.now(timezone.utc).isoformat()}

    if critical_down:
        return True, "critical_service_down", {**evidence, "critical_down": True}

    if data_age_s is not None and data_age_s > float(lim["max_data_age_s"]):
        return True, "stale_market_data", {**evidence, "data_age_s": data_age_s}

    if recent_binance_errors >= int(lim["max_binance_errors"]):
        return True, "repeated_binance_errors", {
            **evidence,
            "errors": recent_binance_errors,
        }

    if missing_marks >= int(lim["max_missing_marks"]):
        return True, "valuation_problems", {**evidence, "missing_marks": missing_marks}

    total = cash + invested_cost
    if total > 0:
        exposure_pct = (invested_cost / total) * 100
        evidence["gross_exposure_pct"] = exposure_pct
        if exposure_pct > float(lim["max_gross_exposure_pct"]):
            return True, "excessive_portfolio_risk", evidence

    # drawdown from equity series
    if equity_series:
        peak = equity_series[0]
        max_dd = 0.0
        for e in equity_series:
            peak = max(peak, e)
            if peak > 0:
                max_dd = min(max_dd, (e - peak) / peak * 100)
        evidence["max_drawdown_pct"] = max_dd
        if abs(max_dd) >= float(lim["max_drawdown_pct"]):
            return True, "max_drawdown", evidence

    if (
        equity is not None
        and day_start_equity is not None
        and day_start_equity > 0
    ):
        daily_loss_pct = (equity - day_start_equity) / day_start_equity * 100
        evidence["daily_pnl_pct"] = daily_loss_pct
        if daily_loss_pct <= -float(lim["max_daily_loss_pct"]):
            return True, "max_daily_loss", evidence

    if equity is not None and initial_capital > 0:
        from_peak = (equity - initial_capital) / initial_capital * 100
        evidence["vs_initial_pct"] = from_peak

    return False, None, evidence


def persist_breaker_state(
    execute: Callable,
    *,
    active: bool,
    reason: str | None,
    evidence: dict[str, Any],
) -> None:
    import json

    execute(
        """INSERT INTO circuit_breaker_state(id, active, reason, evidence_json, updated_at)
           VALUES(1, %s, %s, %s::jsonb, NOW())
           ON CONFLICT(id) DO UPDATE SET
             active=EXCLUDED.active,
             reason=EXCLUDED.reason,
             evidence_json=EXCLUDED.evidence_json,
             updated_at=NOW()""",
        (active, reason, json.dumps(evidence)),
    )
    if active and reason:
        execute(
            """INSERT INTO circuit_breaker_events(at, reason, evidence_json, action)
               VALUES(NOW(), %s, %s::jsonb, 'trip')""",
            (reason, json.dumps(evidence)),
        )


def recovery_allowed(
    *,
    active: bool,
    reason: str | None,
    evidence: dict[str, Any],
    recheck: tuple[bool, str | None, dict[str, Any]],
) -> tuple[bool, str]:
    """
    Documented recovery: only when re-evaluation no longer trips AND reason was not
    'manual_lock'. Manual locks require explicit API clear.
    """
    if not active:
        return True, "already_clear"
    if reason == "manual_lock":
        return False, "manual_lock_requires_explicit_clear"
    block, new_reason, _ = recheck
    if block:
        return False, f"still_tripped:{new_reason}"
    return True, "conditions_cleared"
