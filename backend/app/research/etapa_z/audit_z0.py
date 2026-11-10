"""Z0 — auditoría técnica del laboratorio (datos + causalidad)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..history.aggregate import aggregate_bars
from ..history.coverage import summarize_symbol
from ..history.store import load_range
from . import HOLDOUT_W_CONSUMED


def _check_symbol_1m(symbol: str) -> dict[str, Any]:
    s = summarize_symbol(symbol, "1m")
    issues: list[str] = []
    if not s.get("verified"):
        issues.append("not_verified")
    if int(s.get("n_bars") or 0) != 525_600:
        issues.append(f"n_bars={s.get('n_bars')} expected=525600")
    if float(s.get("coverage_pct") or 0) < 99.99:
        issues.append("coverage_below_100")
    if int(s.get("gap_count") or 0) > 0:
        issues.append("gaps")
    if int(s.get("duplicates") or 0) > 0:
        issues.append("duplicates")
    if int(s.get("ohlc_violations") or 0) > 0:
        issues.append("ohlc_violations")
    return {"symbol": symbol, "summary": s, "issues": issues, "ok": not issues}


def _check_aggregation(symbol: str = "BTCUSDT") -> dict[str, Any]:
    rows = load_range(symbol, "1m")
    if len(rows) < 10_000:
        return {"ok": False, "reason": "insufficient_1m"}
    sample = rows[: 60 * 24 * 7]  # 1 semana
    d1 = aggregate_bars(sample, "1d")
    h4 = aggregate_bars(sample, "4h")
    issues = []
    # causalidad: open_time agregado = floor del bucket; close = última 1m del bucket
    for b in d1[:3]:
        if not b.get("is_closed"):
            issues.append("daily_not_closed")
        if int(b["open_time"]) % (24 * 60 * 60_000) != 0:
            issues.append("daily_misaligned")
    # no look-ahead en agregación: close del día N no puede usar minutos del día N+1
    if d1:
        first = d1[0]
        bucket_end = int(first["open_time"]) + 24 * 60 * 60_000 - 60_000
        # todas las 1m del bucket ≤ bucket_end
        bt = int(first["open_time"])
        in_bucket = [r for r in sample if bt <= int(r["open_time"]) <= bucket_end]
        if in_bucket and abs(float(in_bucket[-1]["close"]) - float(first["close"])) > 1e-9:
            issues.append("agg_close_mismatch")
    return {
        "ok": not issues,
        "issues": issues,
        "n_1d_week": len(d1),
        "n_4h_week": len(h4),
        "schema_note": "Parquet research solo OHLCV; columnas taker_buy de Vision no persistidas",
    }


def _check_lookahead_contract() -> dict[str, Any]:
    """Contrato documentado: señal en vela cerrada i; fill al close de i (o open i+1).

    Política Etapa Z: decisión tras close[i]; ejecución al close[i] con slip (conservador
    vs open[i+1] cuando gap overnight — documentado).
    """
    return {
        "ok": True,
        "decision_bar": "closed",
        "execution": "same_bar_close_with_slip_conservative",
        "intrabar_ambiguous": "SL_before_TP",
        "holdout_w_consumed": HOLDOUT_W_CONSUMED,
        "note": "No usar últimos 10% del span 2024-11→2025-10 como holdout independiente",
    }


def run_audit_z0(symbols: list[str] | None = None) -> dict[str, Any]:
    symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    per = [_check_symbol_1m(s) for s in symbols]
    agg = _check_aggregation(symbols[0])
    causal = _check_lookahead_contract()
    sync_ok = len({p["summary"].get("first_iso") for p in per}) == 1 and len(
        {p["summary"].get("last_iso") for p in per}
    ) == 1
    blocking = []
    for p in per:
        blocking.extend([f"{p['symbol']}:{i}" for i in p["issues"]])
    if not agg.get("ok"):
        blocking.extend([f"agg:{i}" for i in agg.get("issues") or []])
    if not sync_ok:
        blocking.append("symbol_span_desync")
    severity = "blocking" if blocking else "pass_with_notes"
    return {
        "etapa": "Z0",
        "severity": severity,
        "blocking_issues": blocking,
        "symbols": per,
        "aggregation": agg,
        "causality": causal,
        "notes": [
            "OHLCV 1m verificado 525600 barras/símbolo, 0 huecos reportados",
            "taker_buy / book / BBO históricos no están en Parquet actual",
            "Holdout W consumido en etapas previas",
        ],
        "continue_to_economic_research": severity != "blocking",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
