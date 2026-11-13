"""Etapa AE — continuidad, protección, gaps, recovery policy (fixtures only)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.ops.continuity import classify_gap, reconcile_after_gap, safe_auto_recoveries
from app.ops.health_center import build_continuity_snapshot, protection_status


def test_ae_protection_idle_without_positions():
    gap = classify_gap(10.0, warn_s=180, crit_s=600)
    p = protection_status(
        bot_status="STOPPED",
        open_positions=0,
        gap=gap,
        price_stale=False,
    )
    assert p["entries"] == "ENTRIES_DISABLED"
    assert p["protection"] == "SIN_POSICIONES_QUE_PROTEGER"
    assert p["claims_continuous_coverage"] is False


def test_ae_protection_unavailable_with_open_pos_and_critical_gap():
    gap = classify_gap(900.0, warn_s=180, crit_s=600)
    p = protection_status(
        bot_status="STOPPED",
        open_positions=2,
        gap=gap,
        price_stale=False,
    )
    assert p["entries"] == "ENTRIES_DISABLED"
    assert p["protection"] == "PROTECTION_UNAVAILABLE"
    assert p["claims_continuous_coverage"] is False


def test_ae_protection_available_running_fresh():
    gap = classify_gap(20.0, warn_s=180, crit_s=600)
    p = protection_status(
        bot_status="RUNNING",
        open_positions=1,
        gap=gap,
        price_stale=False,
        entries_authorized=True,
    )
    assert p["entries"] == "ENTRIES_ENABLED"
    assert p["protection"] == "PROTECTION_AVAILABLE"


def test_ae_entries_disabled_when_unauthorized_even_if_running():
    gap = classify_gap(20.0, warn_s=180, crit_s=600)
    p = protection_status(
        bot_status="RUNNING",
        open_positions=1,
        gap=gap,
        price_stale=False,
        entries_authorized=False,
    )
    assert p["entries"] == "ENTRIES_DISABLED"
    assert p["protection"] == "PROTECTION_AVAILABLE"


def test_ae_gap_not_auto_classified_as_windows_suspend():
    r = reconcile_after_gap(gap_s=700, price_age_s=10, open_positions=0)
    assert r["cause_class"] in {"host_or_process_gap_suspected", "elevated_latency", "none"}
    assert "Windows/WSL" in r["cause_note"] or "EBZ" in r["cause_note"]


def test_ae_safe_auto_recoveries_never_reactivate_strategies():
    pol = safe_auto_recoveries()
    assert pol["limits"]["never_reactivate_stopped_strategies"] is True
    assert pol["limits"]["same_host_watchdog_cannot_see_full_host_death"] is True
    assert pol["optional_external_check"]["status"] == "NOT_CONFIGURED"


def test_ae_continuity_snapshot_overall_and_no_false_24_7():
    now = datetime.now(timezone.utc)
    snap = build_continuity_snapshot(
        demo_st={"status": "STOPPED", "heartbeat_at": now, "last_eval_at": now, "last_error": None},
        active_st={"status": "STOPPED", "heartbeat_at": now, "last_eval_at": now, "last_error": None},
        demo_pos_n=0,
        active_pos_n=0,
        price_age_s=5.0,
        shadow_hb=now,
        worker_scan_age_s=10.0,
    )
    assert snap["overall"] == "OK_SNAPSHOT"
    assert snap["verification_levels"]["pending_longitudinal_observation"] is True
    assert snap["services"]["demo_runner"]["entries_protection"]["entries"] == "ENTRIES_DISABLED"


def test_ae_stale_heartbeat_marks_degraded():
    old = datetime.now(timezone.utc) - timedelta(seconds=900)
    snap = build_continuity_snapshot(
        demo_st={"status": "STOPPED", "heartbeat_at": old, "last_eval_at": old},
        active_st={"status": "STOPPED", "heartbeat_at": old, "last_eval_at": old},
        demo_pos_n=1,
        active_pos_n=0,
        price_age_s=5.0,
    )
    assert snap["overall"] == "DEGRADED"
    assert (
        snap["services"]["demo_runner"]["entries_protection"]["protection"]
        == "PROTECTION_UNAVAILABLE"
    )
    assert any(a.get("severity") == "CRITICAL" for a in snap["critical_alerts"])
