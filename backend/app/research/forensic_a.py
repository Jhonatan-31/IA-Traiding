"""Auditoría forense de operaciones A — reconstrucción desde libro de trades."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..active.economic_audit import _f, _fifo_rounds, audit_strategy_a


def reconstruct_equity_from_trades(trades: list[dict[str, Any]], initial: float = 1000.0) -> dict[str, Any]:
    """Reconstruye cash/equity mark-to-cost desde fills (sin double-count de slip).

    Modelo contable del motor Demo:
    - BUY: cash -= qty*price + fee  (price ya incluye efecto de slip en fill)
    - SELL: cash += qty*price - fee; realized_pnl ya neto de costos de salida vs cost
    Slip se reporta aparte y NO se resta otra vez del cash.
    """
    cash = initial
    positions: dict[str, dict[str, float]] = {}
    path = [{"i": 0, "at": None, "cash": cash, "equity_proxy": cash, "event": "start"}]
    for t in sorted(trades, key=lambda r: (r.get("at") or datetime.min.replace(tzinfo=timezone.utc), r.get("id") or 0)):
        side = str(t.get("side") or "").upper()
        sym = str(t.get("symbol") or "")
        qty = _f(t.get("qty"))
        px = _f(t.get("price"))
        fee = _f(t.get("fee"))
        if side == "BUY":
            cash -= qty * px + fee
            positions[sym] = {
                "qty": qty,
                "cost": qty * px,
                "entry": px,
            }
            event = "BUY"
        elif side == "SELL":
            cash += qty * px - fee
            positions.pop(sym, None)
            event = "SELL"
        else:
            continue
        inv = sum(p["cost"] for p in positions.values())
        path.append(
            {
                "i": int(t.get("id") or 0),
                "at": t.get("at"),
                "cash": round(cash, 6),
                "equity_proxy": round(cash + inv, 6),
                "event": event,
                "symbol": sym,
                "realized_pnl_fill": _f(t.get("realized_pnl")) if side == "SELL" else 0.0,
            }
        )
    inv = sum(p["cost"] for p in positions.values())
    return {
        "initial": initial,
        "final_cash": round(cash, 6),
        "final_equity_proxy": round(cash + inv, 6),
        "open_positions": len(positions),
        "path_len": len(path),
        "path_tail": path[-8:],
        "accounting_note": (
            "equity_proxy = cash + costo de posiciones (no MTM). "
            "Slip no se resta dos veces: ya está en el precio de fill."
        ),
    }


def forensic_rounds(execute: Callable) -> dict[str, Any]:
    from ..demo import ACCOUNT_ID as DEMO_ID

    acc = execute("SELECT * FROM demo_accounts WHERE id=%s", (DEMO_ID,)).fetchone()
    trades = [dict(r) for r in execute(
        """SELECT id, at, symbol, side, qty, price, fee, slip, realized_pnl, reason, order_id, meta_json
           FROM demo_trades WHERE account_id=%s ORDER BY id""",
        (DEMO_ID,),
    )]
    closed, open_lots = _fifo_rounds(trades)
    initial = _f((acc or {}).get("initial_capital"), 1000.0)
    book = reconstruct_equity_from_trades(trades, initial=initial)
    db_cash = _f((acc or {}).get("cash"))

    # Enrich rounds with gross/net attribution
    enriched = []
    for c in closed:
        entry_px = _f(c.get("entry_price"))
        exit_px = _f(c.get("exit_price"))
        qty = _f(c.get("qty"))
        fees = _f(c.get("fees"))
        slip = _f(c.get("slip"))
        rpnl = _f(c.get("realized_pnl"))  # already net of exit vs entry cost in engine
        # Gross price move before fees (using fill prices which embed slip)
        gross_move = (exit_px - entry_px) * qty if entry_px and exit_px else None
        enriched.append(
            {
                "symbol": c["symbol"],
                "entry_at": c["entry_at"].isoformat() if hasattr(c["entry_at"], "isoformat") else c["entry_at"],
                "exit_at": c["exit_at"].isoformat() if hasattr(c["exit_at"], "isoformat") else c["exit_at"],
                "signal_price_note": "El motor Demo no guarda precio de señal aparte; fill≈señal±slip.",
                "entry_price_executed": entry_px,
                "exit_price_executed": exit_px,
                "qty": qty,
                "entry_fee_alloc": None,  # filled below
                "fees_round": round(fees, 6),
                "slip_round": round(slip, 6),
                "pnl_gross_price_move": round(gross_move, 6) if gross_move is not None else None,
                "pnl_net_engine": round(rpnl, 6),
                "entry_reason": c.get("entry_reason"),
                "exit_reason": c.get("exit_reason"),
                "entry_reason_human": c.get("entry_reason_human"),
                "exit_reason_human": c.get("exit_reason_human"),
                "duration_seconds": c.get("duration_seconds"),
                "mfe": None,
                "mae": None,
                "mfe_mae_note": (
                    "MFE/MAE intrabar no persistidos en demo_trades; "
                    "requiere klines entre entrada/salida (enriquecimiento opcional offline)."
                ),
                "regime": None,
                "sell_trade_id": c.get("sell_trade_id"),
            }
        )

    # Fix entry fee: fees_round already is buy+sell; split using sell id
    sell_fees = {int(t["id"]): _f(t.get("fee")) for t in trades if str(t.get("side")) == "SELL"}
    for e in enriched:
        sid = e.get("sell_trade_id")
        sell_fee = sell_fees.get(int(sid)) if sid is not None else 0.0
        e["exit_fee"] = round(sell_fee or 0.0, 6)
        e["entry_fee_alloc"] = round(_f(e["fees_round"]) - _f(e["exit_fee"]), 6)

    # Loss source decomposition (facts)
    sum_net = sum(_f(e["pnl_net_engine"]) for e in enriched)
    sum_fees = sum(_f(e["fees_round"]) for e in enriched)
    sum_slip = sum(_f(e["slip_round"]) for e in enriched)
    by_exit: dict[str, float] = {}
    for e in enriched:
        by_exit[e["exit_reason"] or "unknown"] = by_exit.get(e["exit_reason"] or "unknown", 0.0) + _f(
            e["pnl_net_engine"]
        )

    discrepancy = round(book["final_cash"] - db_cash, 6)
    return {
        "paper_only": True,
        "ledger": DEMO_ID,
        "verified_totals": {
            "buys": sum(1 for t in trades if t["side"] == "BUY"),
            "sells": sum(1 for t in trades if t["side"] == "SELL"),
            "closed_rounds": len(enriched),
            "realized_pnl_sum": round(sum_net, 6),
            "fees_sum": round(sum_fees, 6),
            "slip_sum": round(sum_slip, 6),
            "db_cash": db_cash,
            "reconstructed_cash": book["final_cash"],
            "cash_discrepancy": discrepancy,
            "matches_etapa_u_report": (
                abs(db_cash - 990.805739) < 0.01
                and abs(sum_net - (-7.801774)) < 0.01
                and len(enriched) == 56
            ),
        },
        "equity_book": book,
        "loss_sources": {
            "by_exit_reason_pnl": {k: round(v, 6) for k, v in sorted(by_exit.items(), key=lambda x: x[1])},
            "fees_reported_separately": round(sum_fees, 6),
            "slip_reported_separately": round(sum_slip, 6),
            "interpretation": (
                "El P/L neto del motor ya incluye el efecto del slip en precios de fill y "
                "el fee de salida vía cash. Las comisiones/slip se listan para atribución, "
                "no para restarlas otra vez al patrimonio."
            ),
        },
        "rounds": enriched,
        "open_lots": open_lots,
        "baseline_audit": {
            k: audit_strategy_a(execute).get(k)
            for k in ("capital", "closed_performance", "loss_diagnosis", "by_symbol")
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
