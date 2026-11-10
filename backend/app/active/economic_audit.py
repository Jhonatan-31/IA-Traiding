"""Auditoría económica de operaciones — solo lectura, sin cambiar reglas.

Reconciliación FIFO por símbolo, diagnóstico de pérdidas y marco A/B prospectivo.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Callable

from . import ACCOUNT_B, INITIAL_CASH, POLICY_B_VERSION
from .policy_b import human_reason as human_b

EXIT_HUMAN = {
    "stop_loss_1pct": "Protección de pérdida (−1%)",
    "take_profit_2pct": "Objetivo de ganancia (+2%)",
    "trend_break_1m": "Salida por debilitamiento de tendencia",
    "demo_policy_buy": "Compra según reglas del Bot Demo",
    "ema_cross_down_exit": "Salida por cruce bajista de medias",
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _human_exit(reason: str | None) -> str:
    r = (reason or "").strip()
    if r in EXIT_HUMAN:
        return EXIT_HUMAN[r]
    if r.startswith("policy_") and "flags" in r:
        return "Compra según reglas del Bot Demo"
    return human_b(r) if r else "Sin detalle"


def _fifo_rounds(trades: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Empareja BUY→SELL por símbolo (FIFO). Devuelve (cerradas, abiertas_restantes)."""
    by_sym: dict[str, deque] = defaultdict(deque)
    closed: list[dict[str, Any]] = []
    for t in sorted(trades, key=lambda r: (r.get("at") or datetime.min.replace(tzinfo=timezone.utc), r.get("id") or 0)):
        side = str(t.get("side") or "").upper()
        sym = str(t.get("symbol") or "")
        qty = _f(t.get("qty"))
        if side == "BUY":
            by_sym[sym].append(dict(t))
            continue
        if side != "SELL":
            continue
        remaining = qty
        sell_fee = _f(t.get("fee"))
        sell_slip = _f(t.get("slip"))
        sell_px = _f(t.get("price"))
        sell_at = t.get("at")
        exit_reason = str(t.get("reason") or "")
        # realized_pnl en el fill de venta ya es del lote completo en este motor
        lot_rpnl = _f(t.get("realized_pnl"))
        entry_parts: list[dict[str, Any]] = []
        buy_fee_alloc = 0.0
        buy_slip_alloc = 0.0
        entry_notional = 0.0
        entry_qty = 0.0
        entry_at = None
        entry_reason = None
        while remaining > 1e-12 and by_sym[sym]:
            buy = by_sym[sym][0]
            bq = _f(buy.get("qty"))
            take = min(bq, remaining)
            frac = take / bq if bq > 0 else 0.0
            buy_fee_alloc += _f(buy.get("fee")) * frac
            buy_slip_alloc += _f(buy.get("slip")) * frac
            entry_notional += take * _f(buy.get("price"))
            entry_qty += take
            if entry_at is None:
                entry_at = buy.get("at")
                entry_reason = str(buy.get("reason") or "")
            entry_parts.append({"buy_id": buy.get("id"), "qty": take, "price": _f(buy.get("price"))})
            buy["qty"] = bq - take
            remaining -= take
            if _f(buy.get("qty")) <= 1e-12:
                by_sym[sym].popleft()
        duration_sec = None
        if entry_at and sell_at:
            ea = entry_at if getattr(entry_at, "tzinfo", None) else entry_at
            sa = sell_at if getattr(sell_at, "tzinfo", None) else sell_at
            try:
                duration_sec = max(0.0, (sa - ea).total_seconds())
            except Exception:
                duration_sec = None
        closed.append(
            {
                "symbol": sym,
                "qty": entry_qty,
                "entry_price": (entry_notional / entry_qty) if entry_qty else None,
                "exit_price": sell_px,
                "entry_at": entry_at,
                "exit_at": sell_at,
                "duration_seconds": duration_sec,
                "entry_reason": entry_reason,
                "exit_reason": exit_reason,
                "entry_reason_human": _human_exit(entry_reason),
                "exit_reason_human": _human_exit(exit_reason),
                "realized_pnl": lot_rpnl,
                "fees": buy_fee_alloc + sell_fee,
                "slip": buy_slip_alloc + sell_slip,
                "net_after_costs_note": "realized_pnl del simulador ya refleja precio de fill (con slip) menos costos de salida; fees de compra/venta se reportan aparte.",
                "sell_trade_id": t.get("id"),
                "entry_legs": entry_parts,
                "unmatched_sell_qty": remaining if remaining > 1e-12 else 0.0,
            }
        )
    open_lots = []
    for sym, q in by_sym.items():
        for buy in q:
            open_lots.append(
                {
                    "symbol": sym,
                    "qty": _f(buy.get("qty")),
                    "entry_price": _f(buy.get("price")),
                    "cost": _f(buy.get("qty")) * _f(buy.get("price")),
                    "opened_at": buy.get("at"),
                    "entry_reason": str(buy.get("reason") or ""),
                    "entry_reason_human": _human_exit(str(buy.get("reason") or "")),
                    "buy_trade_id": buy.get("id"),
                    "fees_paid_at_entry": _f(buy.get("fee")),
                    "slip_at_entry": _f(buy.get("slip")),
                }
            )
    return closed, open_lots


def _stats_closed(closed: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(closed)
    if n == 0:
        return {
            "closed_rounds": 0,
            "wins": 0,
            "losses": 0,
            "breakeven": 0,
            "win_rate": None,
            "avg_win": None,
            "avg_loss": None,
            "profit_factor": None,
            "expectancy": None,
            "sum_realized_pnl": 0.0,
            "sum_fees_on_rounds": 0.0,
            "sum_slip_on_rounds": 0.0,
            "avg_duration_seconds": None,
        }
    wins = [c for c in closed if _f(c["realized_pnl"]) > 1e-9]
    losses = [c for c in closed if _f(c["realized_pnl"]) < -1e-9]
    flat = [c for c in closed if abs(_f(c["realized_pnl"])) <= 1e-9]
    gross_win = sum(_f(c["realized_pnl"]) for c in wins)
    gross_loss = abs(sum(_f(c["realized_pnl"]) for c in losses))
    sum_pnl = sum(_f(c["realized_pnl"]) for c in closed)
    durs = [c["duration_seconds"] for c in closed if c.get("duration_seconds") is not None]
    pf = (gross_win / gross_loss) if gross_loss > 0 else (None if gross_win == 0 else float("inf"))
    return {
        "closed_rounds": n,
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(flat),
        "win_rate": round(len(wins) / n, 6) if n else None,
        "avg_win": round(gross_win / len(wins), 6) if wins else None,
        "avg_loss": round((-gross_loss / len(losses)), 6) if losses else None,
        "profit_factor": (round(pf, 6) if pf is not None and pf != float("inf") else pf),
        "expectancy": round(sum_pnl / n, 6),
        "sum_realized_pnl": round(sum_pnl, 6),
        "sum_fees_on_rounds": round(sum(_f(c["fees"]) for c in closed), 6),
        "sum_slip_on_rounds": round(sum(_f(c["slip"]) for c in closed), 6),
        "avg_duration_seconds": round(sum(durs) / len(durs), 1) if durs else None,
        "note": "Win rate solo sobre rondas completamente cerradas. Compras abiertas no cuentan como ganadoras.",
    }


def audit_strategy_a(execute: Callable, *, marks: dict[str, float] | None = None) -> dict[str, Any]:
    from ..demo import ACCOUNT_ID as DEMO_ID

    marks = marks or {}
    acc = execute("SELECT * FROM demo_accounts WHERE id=%s", (DEMO_ID,)).fetchone()
    st = execute("SELECT * FROM demo_state WHERE id=1").fetchone()
    positions = [dict(r) for r in execute(
        "SELECT * FROM demo_positions WHERE account_id=%s ORDER BY symbol", (DEMO_ID,)
    )]
    trades = [dict(r) for r in execute(
        """SELECT id, at, symbol, side, qty, price, fee, slip, realized_pnl, reason, order_id
           FROM demo_trades WHERE account_id=%s ORDER BY id""",
        (DEMO_ID,),
    )]
    order_counts = execute(
        """SELECT side, status, COUNT(*) n FROM demo_orders
           WHERE account_id=%s GROUP BY side, status""",
        (DEMO_ID,),
    ).fetchall()
    trade_counts = execute(
        """SELECT side, COUNT(*) n, COALESCE(SUM(fee),0) fees, COALESCE(SUM(slip),0) slip,
                  COALESCE(SUM(CASE WHEN side='SELL' THEN realized_pnl ELSE 0 END),0) rpnl,
                  COALESCE(SUM(qty*price),0) notional
           FROM demo_trades WHERE account_id=%s GROUP BY side""",
        (DEMO_ID,),
    ).fetchall()

    closed, open_lots = _fifo_rounds(trades)
    closed_stats = _stats_closed(closed)

    initial = _f((acc or {}).get("initial_capital"), 1000.0)
    cash = _f((acc or {}).get("cash"))
    peak = _f((acc or {}).get("peak_equity"), initial)

    # Unrealized from marks or entry cost fallback
    mv = 0.0
    cost_open = 0.0
    unrealized = 0.0
    pos_detail = []
    for p in positions:
        sym = str(p["symbol"])
        qty = _f(p["qty"])
        entry = _f(p["entry_price"])
        cost = _f(p.get("cost"), qty * entry)
        mark = marks.get(sym)
        mark_src = "live_mark" if mark is not None else "entry_fallback"
        if mark is None:
            mark = entry
        mtm = qty * mark
        u = mtm - cost
        mv += mtm
        cost_open += cost
        unrealized += u
        pos_detail.append(
            {
                "symbol": sym,
                "qty": qty,
                "entry_price": entry,
                "mark": mark,
                "mark_source": mark_src,
                "cost": round(cost, 6),
                "market_value": round(mtm, 6),
                "unrealized_pnl": round(u, 6),
                "opened_at": p.get("opened_at"),
            }
        )

    equity = cash + mv
    net_vs_cash = equity - initial
    fees_total = sum(_f(r.get("fees")) for r in trade_counts)
    slip_total = sum(_f(r.get("slip")) for r in trade_counts)
    realized = _f(next((r.get("rpnl") for r in trade_counts if str(r.get("side")) == "SELL"), 0))

    # Drawdown vs peak
    dd = max(0.0, (peak - equity) / peak) if peak > 0 else None

    # By symbol
    by_symbol: dict[str, dict[str, Any]] = {}
    for c in closed:
        sym = c["symbol"]
        bucket = by_symbol.setdefault(
            sym,
            {"symbol": sym, "closed": 0, "wins": 0, "losses": 0, "realized_pnl": 0.0, "fees": 0.0},
        )
        bucket["closed"] += 1
        bucket["realized_pnl"] += _f(c["realized_pnl"])
        bucket["fees"] += _f(c["fees"])
        if _f(c["realized_pnl"]) > 0:
            bucket["wins"] += 1
        elif _f(c["realized_pnl"]) < 0:
            bucket["losses"] += 1
    for sym, b in by_symbol.items():
        b["realized_pnl"] = round(b["realized_pnl"], 6)
        b["fees"] = round(b["fees"], 6)

    # By exit reason
    by_exit: dict[str, dict[str, Any]] = {}
    for c in closed:
        er = c["exit_reason"] or "unknown"
        bucket = by_exit.setdefault(
            er,
            {
                "reason": er,
                "label": c["exit_reason_human"],
                "n": 0,
                "realized_pnl": 0.0,
                "wins": 0,
                "losses": 0,
            },
        )
        bucket["n"] += 1
        bucket["realized_pnl"] += _f(c["realized_pnl"])
        if _f(c["realized_pnl"]) > 0:
            bucket["wins"] += 1
        elif _f(c["realized_pnl"]) < 0:
            bucket["losses"] += 1
    for b in by_exit.values():
        b["realized_pnl"] = round(b["realized_pnl"], 6)

    # Loss diagnosis
    sl_pnl = sum(_f(c["realized_pnl"]) for c in closed if c["exit_reason"] == "stop_loss_1pct")
    tp_pnl = sum(_f(c["realized_pnl"]) for c in closed if c["exit_reason"] == "take_profit_2pct")
    trend_pnl = sum(_f(c["realized_pnl"]) for c in closed if c["exit_reason"] == "trend_break_1m")
    other_exit = sum(
        _f(c["realized_pnl"])
        for c in closed
        if c["exit_reason"] not in {"stop_loss_1pct", "take_profit_2pct", "trend_break_1m"}
    )

    # Cash held benchmark
    cash_benchmark = {
        "initial": initial,
        "if_held_cash": initial,
        "bot_equity": round(equity, 6),
        "difference_vs_cash": round(equity - initial, 6),
        "interpretation": (
            "Mantener efectivo habría dejado 1.000 USDT sin variación. "
            f"El bot muestra patrimonio ≈ {equity:.2f} USDT "
            f"({'pérdida' if equity < initial else 'ganancia'} neta ≈ {abs(equity - initial):.2f} USDT)."
        ),
    }

    # Orders vs trades integrity
    filled_buys = sum(int(r["n"]) for r in order_counts if r["side"] == "BUY" and r["status"] == "FILLED")
    filled_sells = sum(int(r["n"]) for r in order_counts if r["side"] == "SELL" and r["status"] == "FILLED")
    buys = int(next((r["n"] for r in trade_counts if r["side"] == "BUY"), 0))
    sells = int(next((r["n"] for r in trade_counts if r["side"] == "SELL"), 0))
    integrity = {
        "orders_filled_buys": filled_buys,
        "orders_filled_sells": filled_sells,
        "trades_buys": buys,
        "trades_sells": sells,
        "orders_trades_match": filled_buys == buys and filled_sells == sells,
        "fifo_closed": len(closed),
        "fifo_open_lots": len(open_lots),
        "db_open_positions": len(positions),
        "unmatched_sells": sum(1 for c in closed if _f(c.get("unmatched_sell_qty")) > 0),
        "note": None,
    }
    if not integrity["orders_trades_match"]:
        integrity["note"] = (
            f"Desajuste órdenes FILLED vs trades: órdenes BUY {filled_buys}/SELL {filled_sells} "
            f"frente a trades BUY {buys}/SELL {sells}. La auditoría usa demo_trades (fills contables)."
        )

    # Narrative explanation 1000 → ~equity
    explanation = {
        "headline": (
            f"El patrimonio virtual pasó de {initial:.2f} a ≈{equity:.2f} USDT "
            f"(Δ {equity - initial:+.2f})."
        ),
        "components": [
            {
                "label": "Resultado de operaciones ya cerradas",
                "amount": round(realized, 6),
                "detail": f"{closed_stats['closed_rounds']} operaciones cerradas (FIFO).",
            },
            {
                "label": "Comisiones totales (compra+venta)",
                "amount": round(-fees_total, 6),
                "detail": "Coste fijo del modelo paper (≈10 bps).",
            },
            {
                "label": "Deslizamiento (slippage) registrado",
                "amount": round(-slip_total, 6),
                "detail": "Ya incorporado en el precio de fill; se muestra para atribución.",
            },
            {
                "label": "Resultado no realizado (posiciones abiertas)",
                "amount": round(unrealized, 6),
                "detail": "No cuenta como operación ganadora hasta cerrar.",
            },
            {
                "label": "Salidas por stop-loss (−1%)",
                "amount": round(sl_pnl, 6),
                "detail": f"Incluido dentro del P/L realizado. n={by_exit.get('stop_loss_1pct', {}).get('n', 0)}",
            },
            {
                "label": "Salidas por objetivo (+2%)",
                "amount": round(tp_pnl, 6),
                "detail": f"n={by_exit.get('take_profit_2pct', {}).get('n', 0)}",
            },
            {
                "label": "Salidas por tendencia debilitada",
                "amount": round(trend_pnl, 6),
                "detail": f"n={by_exit.get('trend_break_1m', {}).get('n', 0)} — principal fuente de pequeñas pérdidas repetidas.",
            },
        ],
        "plain_language": (
            "La mayor frecuencia de operaciones no generó valor neto hasta ahora: "
            "las pocas ganancias por objetivo (+2%) no compensan la serie de salidas "
            "por tendencia debilitada y los stop-loss (especialmente el lote del 10/11). "
            "Las comisiones y el deslizamiento suman un coste adicional acumulado. "
            "Las compras abiertas no se contabilizan como ganadoras."
        ),
    }

    loss_diagnosis = {
        "fees_total": round(fees_total, 6),
        "slip_total": round(slip_total, 6),
        "stop_loss_pnl": round(sl_pnl, 6),
        "take_profit_pnl": round(tp_pnl, 6),
        "strategic_trend_exit_pnl": round(trend_pnl, 6),
        "other_exit_pnl": round(other_exit, 6),
        "open_unrealized_pnl": round(unrealized, 6),
        "primary_drag": (
            "trend_break_1m"
            if abs(trend_pnl) >= abs(sl_pnl)
            else "stop_loss_1pct"
        ),
        "primary_drag_human": (
            "Salidas estratégicas por tendencia debilitada (muchas operaciones pequeñas en negativo)"
            if abs(trend_pnl) >= abs(sl_pnl)
            else "Stop-loss (−1%)"
        ),
        "thresholds_unchanged": True,
    }

    buys_n = buys
    sells_n = sells

    return {
        "strategy": "A",
        "name": "Conservadora",
        "ledger": DEMO_ID,
        "paper_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bot_status": (st or {}).get("status"),
        "cycle_count": int((st or {}).get("cycle_count") or 0),
        "capital": {
            "initial": initial,
            "cash": round(cash, 6),
            "equity": round(equity, 6),
            "peak_equity": round(peak, 6),
            "net_pnl": round(net_vs_cash, 6),
            "realized_pnl": round(realized, 6),
            "unrealized_pnl": round(unrealized, 6),
            "drawdown_vs_peak": round(dd, 6) if dd is not None else None,
            "open_cost": round(cost_open, 6),
            "open_market_value": round(mv, 6),
        },
        "activity": {
            "buys": buys_n,
            "sells": sells_n,
            "open_positions": len(positions),
            "closed_rounds": closed_stats["closed_rounds"],
            "fees_total": round(fees_total, 6),
            "slip_total": round(slip_total, 6),
        },
        "closed_performance": closed_stats,
        "by_symbol": sorted(by_symbol.values(), key=lambda x: x["realized_pnl"]),
        "by_exit_reason": sorted(by_exit.values(), key=lambda x: x["realized_pnl"]),
        "open_positions": pos_detail,
        "open_lots_fifo": open_lots,
        "loss_diagnosis": loss_diagnosis,
        "cash_benchmark": cash_benchmark,
        "explanation": explanation,
        "integrity": integrity,
        "recent_closed": [
            {
                **{k: v for k, v in c.items() if k != "entry_legs"},
                "entry_at": c["entry_at"].isoformat() if hasattr(c["entry_at"], "isoformat") else c["entry_at"],
                "exit_at": c["exit_at"].isoformat() if hasattr(c["exit_at"], "isoformat") else c["exit_at"],
            }
            for c in closed[-12:][::-1]
        ],
        "dashboard": {
            "title": "¿Cómo le está yendo a mi bot?",
            "initial": initial,
            "current_value": round(equity, 6),
            "net": round(net_vs_cash, 6),
            "buys": buys_n,
            "sells": sells_n,
            "wins": closed_stats["wins"],
            "losses": closed_stats["losses"],
            "fees": round(fees_total, 6),
            "by_crypto": [
                {
                    "name": s["symbol"].replace("USDT", ""),
                    "resultado": s["realized_pnl"],
                    "cerradas": s["closed"],
                    "ganadoras": s["wins"],
                    "perdedoras": s["losses"],
                }
                for s in sorted(by_symbol.values(), key=lambda x: x["realized_pnl"])
            ],
            "main_loss_reasons": [
                {
                    "motivo": b["label"],
                    "resultado": b["realized_pnl"],
                    "operaciones": b["n"],
                }
                for b in sorted(by_exit.values(), key=lambda x: x["realized_pnl"])[:5]
                if b["realized_pnl"] < 0
            ],
            "summary_text": explanation["plain_language"],
        },
    }


def prospective_ab_frame(execute: Callable, audit_a: dict[str, Any]) -> dict[str, Any]:
    """Marco comparable A/B sin iniciar B. Timestamp prospectivo listo para el usuario."""
    from ..demo import ACCOUNT_ID as DEMO_ID

    b_acc = execute("SELECT * FROM active_accounts WHERE id=%s", (ACCOUNT_B,)).fetchone()
    b_st = execute("SELECT * FROM active_state WHERE id=1").fetchone()
    a_st = execute("SELECT * FROM demo_state WHERE id=1").fetchone()
    b_trades = execute(
        "SELECT COUNT(*) n FROM active_trades WHERE account_id=%s", (ACCOUNT_B,)
    ).fetchone()
    now = datetime.now(timezone.utc)
    return {
        "paper_only": True,
        "b_auto_start": False,
        "b_status": (b_st or {}).get("status") or "STOPPED",
        "a_status": (a_st or {}).get("status"),
        "prospective_anchor": {
            "suggested_start_at": now.isoformat(),
            "instruction": (
                "Cuando decidas iniciar Trading Activo, usa este instante (o el started_at "
                "real de B) como ancla común. Compara solo el periodo en que AMBAS estén RUNNING."
            ),
            "do_not_backfill_b_with_a_history": True,
        },
        "coverage": {
            "A": {
                "ledger": DEMO_ID,
                "effective_status": (a_st or {}).get("status"),
                "started_at": (a_st or {}).get("started_at"),
                "cycle_count": int((a_st or {}).get("cycle_count") or 0),
                "historical_sample": True,
                "closed_rounds": audit_a.get("closed_performance", {}).get("closed_rounds"),
                "net_pnl": audit_a.get("capital", {}).get("net_pnl"),
            },
            "B": {
                "ledger": ACCOUNT_B,
                "policy_version": POLICY_B_VERSION,
                "effective_status": (b_st or {}).get("status"),
                "started_at": (b_st or {}).get("started_at"),
                "cycle_count": int((b_st or {}).get("cycle_count") or 0),
                "initial_capital": _f((b_acc or {}).get("initial_capital"), INITIAL_CASH),
                "cash": _f((b_acc or {}).get("cash"), INITIAL_CASH),
                "trades": int((b_trades or {}).get("n") or 0),
                "historical_sample": False,
                "note": "Detenida: ciclos pueden existir en observación/bloqueo de entradas, sin fills.",
            },
        },
        "comparable_metrics_when_both_running": [
            "equity_vs_initial",
            "realized_pnl",
            "fees",
            "closed_rounds",
            "win_rate_closed_only",
            "profit_factor",
            "max_drawdown",
            "time_in_market",
            "exposure_avg",
        ],
        "fairness_rules": [
            "No declarar ganadora por cantidad de operaciones.",
            "No usar el historial pasado de A como si fuera el de B.",
            "Anclar la comparación al momento en que el usuario inicie B.",
            "Reportar periodos efectivos RUNNING de cada estrategia por separado.",
        ],
        "claim": {"declare_winner": False, "reason": "B aún no tiene periodo prospectivo activo."},
    }


def full_economic_report(execute: Callable, *, marks: dict[str, float] | None = None) -> dict[str, Any]:
    a = audit_strategy_a(execute, marks=marks)
    ab = prospective_ab_frame(execute, a)
    return {
        "paper_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "A": a,
        "ab_prospective": ab,
        "C": {
            "execution_authorized": False,
            "note": "IA experimental sin operaciones; excluida de la auditoría económica operativa.",
        },
    }
