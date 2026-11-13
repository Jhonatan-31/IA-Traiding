"""Host suspend / heartbeat gap detection — evidence only; no forced sells."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def heartbeat_gap_seconds(
    heartbeat_at: Any,
    *,
    now: datetime | None = None,
) -> float | None:
    """Seconds since last heartbeat, or None if unknown."""
    hb = _parse_dt(heartbeat_at)
    if hb is None:
        return None
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0.0, (ref - hb).total_seconds())


def classify_gap(
    gap_s: float | None,
    *,
    warn_s: float = 180.0,
    crit_s: float = 600.0,
    expected_every_s: float | None = None,
) -> dict[str, Any]:
    """
    Classify a heartbeat gap.

    Does NOT claim protective stops were active during the gap.
    """
    if gap_s is None:
        return {
            "status": "UNKNOWN",
            "gap_s": None,
            "host_suspend_suspected": False,
            "note": "sin_heartbeat",
            "safe_to_trade_entries": False,
            "protective_coverage_claimed": False,
        }
    status = "OK"
    if gap_s >= crit_s:
        status = "CRITICAL"
    elif gap_s >= warn_s:
        status = "WARNING"

    # Heuristic: gap >> expected cycle suggests host sleep / docker kill, not a missed tick.
    expected = expected_every_s or 60.0
    host_suspend_suspected = gap_s >= max(crit_s, expected * 8)

    return {
        "status": status,
        "gap_s": round(gap_s, 3),
        "host_suspend_suspected": host_suspend_suspected,
        "note": (
            "hueco_host_o_proceso"
            if host_suspend_suspected
            else ("latencia_elevada" if status != "OK" else "ok")
        ),
        # Entries must not use stale marks after a gap without fresh market data.
        "safe_to_trade_entries": status == "OK",
        # Never claim continuous SL/TP coverage across an unobserved gap.
        "protective_coverage_claimed": False if status != "OK" else True,
    }


def reconcile_after_gap(
    *,
    gap_s: float | None,
    price_age_s: float | None,
    open_positions: int,
    warn_s: float = 180.0,
    crit_s: float = 600.0,
    stale_price_s: float = 120.0,
) -> dict[str, Any]:
    """Recommended actions after detecting a gap — advisory only."""
    gap = classify_gap(gap_s, warn_s=warn_s, crit_s=crit_s)
    stale_prices = price_age_s is None or price_age_s >= stale_price_s
    actions: list[str] = []
    if gap["status"] != "OK":
        actions.append("registrar_hueco")
        actions.append("impedir_entradas_con_datos_obsoletos")
        if open_positions > 0:
            actions.append("evaluar_protecciones_con_precio_fresco")
            actions.append("no_afirmar_cobertura_durante_hueco")
        if stale_prices:
            actions.append("refrescar_mercado_antes_de_operar")
        if gap.get("host_suspend_suspected"):
            actions.append("revisar_reinicio_host_docker_o_suspend")
    return {
        **gap,
        "price_age_s": price_age_s,
        "stale_prices": stale_prices,
        "open_positions": open_positions,
        "recommended_actions": actions,
        "cause_class": (
            "host_or_process_gap_suspected"
            if gap.get("host_suspend_suspected")
            else ("elevated_latency" if gap.get("status") != "OK" else "none")
        ),
        "cause_note": (
            "No clasificar automáticamente todo hueco como suspensión Windows/WSL. "
            "En EBZ nativo Linux, preferir reinicio host/Docker/proceso/red/indeterminado."
        ),
    }


def safe_auto_recoveries() -> dict[str, Any]:
    """Document what may auto-recover vs needs human intervention."""
    return {
        "safe_automatic": [
            "docker_restart_unless_stopped_for_crashed_container",
            "websocket_reconnect_inside_market_stream_hub",
            "db_client_retry_on_transient_errors_if_implemented_by_caller",
        ],
        "requires_human": [
            "host_powered_off",
            "disk_full",
            "corrupt_volume",
            "auth_misconfiguration",
            "strategy_state_change_running",
            "external_alert_when_entire_host_down",
        ],
        "limits": {
            "no_indefinite_restart_storms": True,
            "never_reactivate_stopped_strategies": True,
            "never_restart_foreign_stacks": True,
            "same_host_watchdog_cannot_see_full_host_death": True,
        },
        "optional_external_check": {
            "proposed": "HTTP probe to :8090/api/health from another host/Tailscale node",
            "status": "NOT_CONFIGURED",
            "note": "No contratar ni conectar servicios externos sin autorización.",
        },
    }
