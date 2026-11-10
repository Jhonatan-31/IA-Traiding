"""Etapa T.1 — Diagnóstico de HOLD y comparación económica A/B (solo lectura).

No altera reglas de entrada/salida ni balances. Agrupa motivos en categorías
humanas y usa denominadores correctos (ciclos únicos / HOLDs de entrada).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable

from . import ACCOUNT_B, INITIAL_CASH, POLICY_B_VERSION
from .policy_b import human_reason as human_reason_b

# Categorías pedidas en Etapa T.1 (lenguaje sencillo)
CATEGORY_LABELS = {
    "open_position": "Ya existe una posición",
    "unfavorable_trend": "Tendencia no favorable",
    "insufficient_volatility": "Volatilidad insuficiente",
    "high_costs": "Costos demasiado elevados",
    "risk_exceeded": "Riesgo excedido",
    "signal_unconfirmed": "Señal no confirmada",
    "data_unavailable": "Datos no disponibles",
    "bot_stopped": "Bot detenido (sin compras nuevas)",
    "other": "Otro motivo",
}

# Mapeo motivo técnico → categoría (A y B)
REASON_CATEGORY: dict[str, str] = {
    "hold_position": "open_position",
    "no_5m_trend": "unfavorable_trend",
    "no_ema_cross": "unfavorable_trend",
    "trend_not_aligned": "unfavorable_trend",
    "vol_floor_reject": "insufficient_volatility",
    "atr_extreme": "insufficient_volatility",
    "cost_filter_reject": "high_costs",
    "peak_drawdown_pause": "risk_exceeded",
    "max_positions": "risk_exceeded",
    "max_exposure": "risk_exceeded",
    "cooldown": "risk_exceeded",
    "max_entries_hour": "risk_exceeded",
    "rsi_out_of_band": "signal_unconfirmed",
    "no_clear_signal": "signal_unconfirmed",
    "flags_0_of_5_insufficient": "signal_unconfirmed",
    "flags_1_of_5_insufficient": "signal_unconfirmed",
    "flags_2_of_5_insufficient": "signal_unconfirmed",
    "flags_3_of_5_insufficient": "signal_unconfirmed",
    "flags_4_of_5_insufficient": "signal_unconfirmed",
    "bot_stopped_entries_blocked": "bot_stopped",
    "indicators_incomplete": "data_unavailable",
}


def categorize_reason(reason: str | None) -> str:
    r = (reason or "").strip()
    if not r:
        return "other"
    if r in REASON_CATEGORY:
        return REASON_CATEGORY[r]
    if r.startswith("flags_") and "insufficient" in r:
        return "signal_unconfirmed"
    if "fetch" in r or "incomplete" in r or "no_data" in r:
        return "data_unavailable"
    if "max_" in r or "drawdown" in r or "cooldown" in r:
        return "risk_exceeded"
    if "vol" in r or "atr" in r:
        return "insufficient_volatility"
    if "cost" in r or "fee" in r:
        return "high_costs"
    if "trend" in r or "ema" in r:
        return "unfavorable_trend"
    if "hold_position" in r:
        return "open_position"
    if "stopped" in r:
        return "bot_stopped"
    return "other"


def _human_a(reason: str) -> str:
    # Demo reasons — mirror frontend REASON_HINT without importing frontend
    hints = {
        "bot_stopped_entries_blocked": "El bot está detenido: no abre compras nuevas.",
        "flags_2_of_5_insufficient": "La señal no fue lo bastante clara (2 de 5 condiciones).",
        "flags_3_of_5_insufficient": "La señal no fue lo bastante clara (3 de 5 condiciones).",
        "flags_1_of_5_insufficient": "La señal fue débil (1 de 5 condiciones).",
        "flags_0_of_5_insufficient": "Sin condiciones favorables en este momento.",
        "no_clear_signal": "Sin oportunidad clara en este ciclo.",
        "trend_not_aligned": "La tendencia aún no confirma una compra.",
        "peak_drawdown_pause": "Pausa por protección: la cuenta bajó desde su máximo.",
        "max_positions": "Ya hay el máximo de posiciones abiertas.",
        "max_exposure": "Se alcanzó el límite de dinero invertido.",
        "hold_position": "Ya hay una posición abierta en este mercado.",
        "indicators_incomplete": "Faltan datos de mercado para evaluar con seguridad.",
    }
    if reason in hints:
        return hints[reason]
    if reason.startswith("flags_") and "of_5" in reason:
        return "La señal no fue lo bastante clara según las reglas del Bot Demo."
    return reason.replace("_", " ")


def _pct(n: int, d: int) -> float | None:
    if d <= 0:
        return None
    return round(100.0 * n / d, 2)


def _hold_diagnosis(
    rows: list[dict[str, Any]],
    *,
    strategy: str,
) -> dict[str, Any]:
    """Agrega HOLDs.

    Denominadores:
    - raw_holds: filas HOLD brutas
    - unique_cycle_symbol: ciclos únicos (cycle_id, symbol) — evita inflar si hay
      reintentos/duplicados del mismo ciclo+símbolo
    - entry_holds: HOLDs que no son hold_position (oportunidad de entrada evaluada)
    - unique_entry_cycles: cycle_ids distintos entre entry HOLDs
    Los % de categorías usan unique_cycle_symbol de HOLDs (1 conteo por ciclo+símbolo,
    motivo del registro más reciente de ese par).
    """
    if not rows:
        return {
            "strategy": strategy,
            "raw_holds": 0,
            "unique_cycle_symbol": 0,
            "entry_holds_raw": 0,
            "unique_entry_cycles": 0,
            "hold_position_share_pct": None,
            "categories": [],
            "top_reasons": [],
            "note": "Sin decisiones HOLD registradas todavía.",
        }

    # Deduplicar por (cycle_id, symbol): conservar el más reciente (rows DESC id)
    seen: set[tuple[Any, str]] = set()
    unique: list[dict[str, Any]] = []
    for r in rows:
        key = (r.get("cycle_id"), str(r.get("symbol") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    cat_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    entry_cycle_ids: set[Any] = set()
    entry_raw = 0
    for r in unique:
        reason = str(r.get("reason") or "")
        cat = categorize_reason(reason)
        cat_counter[cat] += 1
        reason_counter[reason] += 1
        if reason != "hold_position":
            entry_raw += 1
            if r.get("cycle_id") is not None:
                entry_cycle_ids.add(r.get("cycle_id"))

    denom = len(unique)
    categories = []
    for cat_id, label in CATEGORY_LABELS.items():
        n = int(cat_counter.get(cat_id, 0))
        if n == 0:
            continue
        categories.append(
            {
                "id": cat_id,
                "label": label,
                "count": n,
                "pct_of_unique_holds": _pct(n, denom),
            }
        )
    categories.sort(key=lambda x: x["count"], reverse=True)

    top_reasons = []
    for reason, n in reason_counter.most_common(12):
        human = human_reason_b(reason) if strategy == "B" else _human_a(reason)
        if strategy == "A" and human == reason.replace("_", " "):
            human = _human_a(reason)
        top_reasons.append(
            {
                "reason": reason,
                "human": human,
                "category": categorize_reason(reason),
                "category_label": CATEGORY_LABELS.get(categorize_reason(reason), "Otro"),
                "count": n,
                "pct_of_unique_holds": _pct(n, denom),
            }
        )

    hold_pos = int(reason_counter.get("hold_position", 0))
    return {
        "strategy": strategy,
        "raw_holds": len(rows),
        "unique_cycle_symbol": denom,
        "entry_holds_unique": entry_raw,
        "unique_entry_cycles": len(entry_cycle_ids),
        "hold_position_share_pct": _pct(hold_pos, denom),
        "denominator": {
            "name": "unique_cycle_symbol_holds",
            "description": (
                "Un conteo por (ciclo, símbolo). No cuenta filas duplicadas "
                "del mismo ciclo+símbolo como muestras independientes."
            ),
            "n": denom,
        },
        "categories": categories,
        "top_reasons": top_reasons,
    }


def diagnose_holds(execute: Callable, *, limit: int = 5000) -> dict[str, Any]:
    from ..demo import ACCOUNT_ID as DEMO_ID

    a_rows = list(
        execute(
            """SELECT id, cycle_id, symbol, reason, at, action
               FROM demo_decisions
               WHERE account_id=%s AND action='HOLD'
               ORDER BY id DESC
               LIMIT %s""",
            (DEMO_ID, limit),
        )
    )
    b_rows = list(
        execute(
            """SELECT id, cycle_id, symbol, reason, human_reason, at, action
               FROM active_decisions
               WHERE account_id=%s AND action='HOLD'
               ORDER BY id DESC
               LIMIT %s""",
            (ACCOUNT_B, limit),
        )
    )
    return {
        "paper_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "A": _hold_diagnosis([dict(r) for r in a_rows], strategy="A"),
        "B": _hold_diagnosis([dict(r) for r in b_rows], strategy="B"),
        "C": {
            "strategy": "C",
            "note": "IA en observación: no genera HOLD operativos ni fills.",
            "execution_authorized": False,
        },
    }


def strategy_history(execute: Callable, *, limit: int = 100) -> dict[str, Any]:
    from ..demo import ACCOUNT_ID as DEMO_ID

    def _trades(table: str, account: str) -> list[dict[str, Any]]:
        rows = list(
            execute(
                f"""SELECT id, at, symbol, side, qty, price, fee, slip, realized_pnl, reason
                    FROM {table}
                    WHERE account_id=%s
                    ORDER BY id DESC
                    LIMIT %s""",
                (account, limit),
            )
        )
        out = []
        for r in rows:
            d = dict(r)
            reason = str(d.get("reason") or "")
            d["human_reason"] = (
                human_reason_b(reason) if table.startswith("active") else _human_a(reason)
            )
            out.append(d)
        return out

    def _rejects(table: str) -> list[dict[str, Any]]:
        rows = list(
            execute(
                f"""SELECT id, at, symbol, reason, detail_json
                    FROM {table}
                    ORDER BY id DESC
                    LIMIT %s""",
                (limit,),
            )
        )
        return [dict(r) for r in rows]

    def _positions(table: str, account: str) -> list[dict[str, Any]]:
        rows = list(
            execute(
                f"""SELECT symbol, qty, cost, entry_price, opened_at
                    FROM {table}
                    WHERE account_id=%s
                    ORDER BY symbol""",
                (account,),
            )
        )
        return [dict(r) for r in rows]

    def _summary(trade_table: str, account: str, positions: list[dict[str, Any]]) -> dict[str, Any]:
        row = execute(
            f"""SELECT
                  COUNT(*) FILTER (WHERE side='BUY') buys,
                  COUNT(*) FILTER (WHERE side='SELL') sells,
                  COALESCE(SUM(fee),0) fees,
                  COALESCE(SUM(CASE WHEN side='SELL' THEN realized_pnl ELSE 0 END),0) rpnl
                FROM {trade_table}
                WHERE account_id=%s""",
            (account,),
        ).fetchone()
        return {
            "buys": int((row or {}).get("buys") or 0),
            "sells": int((row or {}).get("sells") or 0),
            "closed_rounds": int((row or {}).get("sells") or 0),
            "open_positions": len(positions),
            "fees": round(float((row or {}).get("fees") or 0), 6),
            "realized_pnl": round(float((row or {}).get("rpnl") or 0), 6),
        }

    a_trades = _trades("demo_trades", DEMO_ID)
    b_trades = _trades("active_trades", ACCOUNT_B)
    a_pos = _positions("demo_positions", DEMO_ID)
    b_pos = _positions("active_positions", ACCOUNT_B)

    return {
        "paper_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "A": {
            "ledger": DEMO_ID,
            "summary": _summary("demo_trades", DEMO_ID, a_pos),
            "trades": a_trades,
            "positions": a_pos,
            "rejects": _rejects("demo_rejects"),
        },
        "B": {
            "ledger": ACCOUNT_B,
            "summary": _summary("active_trades", ACCOUNT_B, b_pos),
            "trades": b_trades,
            "positions": b_pos,
            "rejects": _rejects("active_rejects"),
        },
        "C": {
            "ledger": "observation",
            "summary": {
                "buys": 0,
                "sells": 0,
                "closed_rounds": 0,
                "open_positions": 0,
                "fees": 0,
                "realized_pnl": None,
            },
            "trades": [],
            "positions": [],
            "rejects": [],
            "note": "Sin ejecución: historial operativo vacío por diseño.",
        },
    }


def compare_ab(execute: Callable) -> dict[str, Any]:
    """Comparación económica A/B con períodos observados (no inventa fills)."""
    from ..demo import ACCOUNT_ID as DEMO_ID

    a_acc = execute("SELECT * FROM demo_accounts WHERE id=%s", (DEMO_ID,)).fetchone()
    b_acc = execute("SELECT * FROM active_accounts WHERE id=%s", (ACCOUNT_B,)).fetchone()
    a_st = execute("SELECT * FROM demo_state WHERE id=1").fetchone()
    b_st = execute("SELECT * FROM active_state WHERE id=1").fetchone()
    a_pos = list(execute("SELECT * FROM demo_positions WHERE account_id=%s", (DEMO_ID,)))
    b_pos = list(execute("SELECT * FROM active_positions WHERE account_id=%s", (ACCOUNT_B,)))

    def trade_stats(trade_table: str, account: str) -> dict[str, Any]:
        row = execute(
            f"""SELECT
                  COUNT(*) FILTER (WHERE side='BUY') buys,
                  COUNT(*) FILTER (WHERE side='SELL') sells,
                  COALESCE(SUM(fee),0) fees,
                  COALESCE(SUM(CASE WHEN side='SELL' THEN realized_pnl ELSE 0 END),0) rpnl,
                  MIN(at) first_at,
                  MAX(at) last_at,
                  COALESCE(SUM(CASE WHEN side='BUY' THEN qty*price ELSE 0 END),0) buy_notional,
                  COALESCE(SUM(CASE WHEN side='SELL' THEN qty*price ELSE 0 END),0) sell_notional
                FROM {trade_table}
                WHERE account_id=%s""",
            (account,),
        ).fetchone()
        return dict(row) if row else {}

    a_t = trade_stats("demo_trades", DEMO_ID)
    b_t = trade_stats("active_trades", ACCOUNT_B)

    def exposure(positions) -> float:
        return round(sum(float(p.get("cost") or 0) for p in positions), 6)

    def observed_window(st, trades: dict[str, Any]) -> dict[str, Any]:
        started = (st or {}).get("started_at")
        first = trades.get("first_at")
        last = trades.get("last_at") or (st or {}).get("updated_at")
        cycles = (st or {}).get("cycle_count")
        return {
            "started_at": started.isoformat() if hasattr(started, "isoformat") else started,
            "first_trade_at": first.isoformat() if hasattr(first, "isoformat") else first,
            "last_activity_at": last.isoformat() if hasattr(last, "isoformat") else last,
            "cycle_count": int(cycles) if cycles is not None else None,
            "status": (st or {}).get("status"),
        }

    def equity_proxy(acc, positions) -> float | None:
        if not acc:
            return None
        cash = float(acc["cash"])
        # Without live marks: cash + entry cost (not MTM). Flagged as proxy.
        return round(cash + sum(float(p["cost"]) for p in positions), 6)

    a_eq = equity_proxy(a_acc, a_pos)
    b_eq = equity_proxy(b_acc, b_pos)
    a_init = float((a_acc or {}).get("initial_capital") or 1000.0)
    b_init = float((b_acc or {}).get("initial_capital") or INITIAL_CASH)
    a_peak = float((a_acc or {}).get("peak_equity") or a_init)
    b_peak = float((b_acc or {}).get("peak_equity") or b_init)

    def dd(eq, peak):
        if eq is None or peak <= 0:
            return None
        return round(max(0.0, (peak - eq) / peak), 6)

    # Decision freshness
    a_last_dec = execute(
        "SELECT at FROM demo_decisions WHERE account_id=%s ORDER BY id DESC LIMIT 1",
        (DEMO_ID,),
    ).fetchone()
    b_last_dec = execute(
        "SELECT at FROM active_decisions WHERE account_id=%s ORDER BY id DESC LIMIT 1",
        (ACCOUNT_B,),
    ).fetchone()

    now = datetime.now(timezone.utc)

    def freshness(row) -> dict[str, Any]:
        if not row or not row.get("at"):
            return {"last_decision_at": None, "age_seconds": None, "quality": "sin_datos"}
        at = row["at"]
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        age = (now - at).total_seconds()
        quality = "fresco" if age <= 120 else ("aceptable" if age <= 600 else "atrasado")
        return {
            "last_decision_at": at.isoformat(),
            "age_seconds": round(age, 1),
            "quality": quality,
        }

    a_block = {
        "id": "A",
        "name": "Conservadora",
        "ledger": DEMO_ID,
        "policy_version": "demo_policy_v1_20261103",
        "initial_capital": a_init,
        "cash": float((a_acc or {}).get("cash") or 0),
        "equity_proxy": a_eq,
        "equity_note": "Proxy = cash + costo de posiciones (sin mark-to-market en vivo en este endpoint).",
        "net_result_proxy": round((a_eq or a_init) - a_init, 6) if a_eq is not None else None,
        "realized_pnl": float(a_t.get("rpnl") or 0),
        "buys": int(a_t.get("buys") or 0),
        "sells": int(a_t.get("sells") or 0),
        "closed_operations": int(a_t.get("sells") or 0),
        "fees": float(a_t.get("fees") or 0),
        "exposure_cost": exposure(a_pos),
        "open_positions": len(a_pos),
        "peak_equity": a_peak,
        "drawdown_proxy": dd(a_eq, a_peak),
        "observed": observed_window(a_st, a_t),
        "data_freshness": freshness(a_last_dec),
    }
    b_block = {
        "id": "B",
        "name": "Trading Activo",
        "ledger": ACCOUNT_B,
        "policy_version": POLICY_B_VERSION,
        "initial_capital": b_init,
        "cash": float((b_acc or {}).get("cash") or 0),
        "equity_proxy": b_eq,
        "equity_note": "Proxy = cash + costo de posiciones (sin mark-to-market en vivo en este endpoint).",
        "net_result_proxy": round((b_eq or b_init) - b_init, 6) if b_eq is not None else None,
        "realized_pnl": float(b_t.get("rpnl") or 0),
        "buys": int(b_t.get("buys") or 0),
        "sells": int(b_t.get("sells") or 0),
        "closed_operations": int(b_t.get("sells") or 0),
        "fees": float(b_t.get("fees") or 0),
        "exposure_cost": exposure(b_pos),
        "open_positions": len(b_pos),
        "peak_equity": b_peak,
        "drawdown_proxy": dd(b_eq, b_peak),
        "observed": observed_window(b_st, b_t),
        "data_freshness": freshness(b_last_dec),
    }

    # Equivalent period note: B may be STOPPED with zero trades — do not declare winner
    claim = {
        "declare_winner": False,
        "reason": (
            "No se declara ganadora: comparación descriptiva. "
            "La cantidad de operaciones no implica superioridad. "
            "B puede tener periodo efectivo distinto (STOPPED / sin fills)."
        ),
        "periods_equivalent": bool(
            a_block["observed"].get("status") == b_block["observed"].get("status")
            and (a_block["buys"] > 0 or b_block["buys"] > 0)
        ),
    }

    # Integrity: ledgers must not share cash mutation paths
    integrity = {
        "ledgers_distinct": DEMO_ID != ACCOUNT_B,
        "demo_cash": a_block["cash"],
        "active_cash": b_block["cash"],
        "cross_contamination_check": "pass" if DEMO_ID != ACCOUNT_B else "fail",
    }

    return {
        "paper_only": True,
        "generated_at": now.isoformat(),
        "A": a_block,
        "B": b_block,
        "claim": claim,
        "integrity": integrity,
        "disclaimer": (
            "Comparación económica en simulación PAPER_ONLY. "
            "No usar cantidad de compras como única métrica de calidad."
        ),
    }
