"""Chart overlays for visualization only — does not drive SMA/Shadow/Lab execution."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _iso(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return str(v)


def build_trade_markers(
    execute: Callable,
    symbol: str,
    *,
    limit_per_source: int = 200,
) -> list[dict[str, Any]]:
    """SMA trades + lab trades + shadow predictions (non-execution)."""
    symbol = symbol.upper().strip()
    out: list[dict[str, Any]] = []

    for row in execute(
        """SELECT id, at, side, qty, price, candle_ms, strategy, reason
           FROM trades WHERE symbol=%s ORDER BY id DESC LIMIT %s""",
        (symbol, limit_per_source),
    ):
        out.append(
            {
                "id": int(row["id"]),
                "ledger": "sma",
                "kind": "execution",
                "at": _iso(row["at"]),
                "side": str(row["side"]).upper(),
                "qty": _f(row["qty"]),
                "price": _f(row["price"]),
                "candle_ms": int(row["candle_ms"]),
                "strategy": row.get("strategy"),
                "reason": row.get("reason"),
                "source": "sma_paper",
                "label": f"SMA {row['side']}",
            }
        )

    for row in execute(
        """SELECT id, at, side, qty, price, candle_ms, strategy, reason
           FROM lab_trades WHERE symbol=%s ORDER BY id DESC LIMIT %s""",
        (symbol, limit_per_source),
    ):
        out.append(
            {
                "id": int(row["id"]),
                "ledger": "lab",
                "kind": "execution",
                "at": _iso(row["at"]),
                "side": str(row["side"]).upper(),
                "qty": _f(row["qty"]),
                "price": _f(row["price"]),
                "candle_ms": int(row["candle_ms"]),
                "strategy": row.get("strategy"),
                "reason": row.get("reason"),
                "source": "lab_auto",
                "label": f"LAB {row['side']}",
            }
        )

    # Prospect shadow decisions — predictions / research, never fills
    for row in execute(
        """SELECT id, created_at, action, strategy, reason, candle_open_ms,
                  observed_price, interval
           FROM prospect_decisions
           WHERE symbol=%s AND UPPER(action) IN ('BUY','SELL')
           ORDER BY id DESC LIMIT %s""",
        (symbol, limit_per_source),
    ):
        side = str(row["action"]).upper()
        out.append(
            {
                "id": int(row["id"]),
                "ledger": "shadow",
                "kind": "prediction",
                "at": _iso(row["created_at"]),
                "side": side,
                "qty": None,
                "price": _f(row.get("observed_price")),
                "candle_ms": int(row["candle_open_ms"]),
                "strategy": row.get("strategy"),
                "reason": row.get("reason"),
                "source": "prospect_shadow",
                "interval": row.get("interval"),
                "label": f"PRED {side}",
            }
        )

    for row in execute(
        """SELECT id, created_at, proposed_action, probability, candle_open_ms,
                  interval, model_version
           FROM ml_predictions
           WHERE symbol=%s
             AND (
               UPPER(proposed_action) LIKE '%%BUY%%'
               OR UPPER(proposed_action) LIKE '%%SELL%%'
             )
           ORDER BY id DESC LIMIT %s""",
        (symbol, min(80, limit_per_source)),
    ):
        pa = str(row["proposed_action"] or "").upper()
        side = "BUY" if "BUY" in pa else "SELL"
        out.append(
            {
                "id": int(row["id"]),
                "ledger": "shadow",
                "kind": "prediction",
                "at": _iso(row["created_at"]),
                "side": side,
                "qty": None,
                "price": None,
                "candle_ms": int(row["candle_open_ms"]),
                "strategy": row.get("model_version") or "ml_shadow",
                "reason": f"proposed={row['proposed_action']} p={row.get('probability')}",
                "source": "ml_predictions",
                "interval": row.get("interval"),
                "label": f"SH {side}",
            }
        )

    out.sort(key=lambda m: (m["candle_ms"], m["id"]))
    return out


def build_open_position_overlays(
    execute: Callable,
    symbol: str,
    *,
    mark_price: float | None = None,
) -> list[dict[str, Any]]:
    """Open positions for chart lines — ledgers never mixed in one object."""
    symbol = symbol.upper().strip()
    now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    overlays: list[dict[str, Any]] = []

    sma = execute("SELECT symbol, qty, cost FROM positions WHERE symbol=%s", (symbol,)).fetchone()
    if sma and _f(sma["qty"]):
        qty = float(sma["qty"])
        cost = float(sma["cost"])
        entry = cost / qty if qty else None
        mark = mark_price
        upnl = (mark - entry) * qty if mark is not None and entry is not None else None
        overlays.append(
            {
                "ledger": "sma",
                "symbol": symbol,
                "qty": qty,
                "entry_price": entry,
                "mark_price": mark,
                "unrealized_pnl": upnl,
                "stop_loss_price": None,
                "take_profit_price": None,
                "stop_loss_pct": None,
                "take_profit_pct": None,
                "opened_at": None,
                "bars_remaining": None,
                "max_hold_bars": None,
                "note": "SMA paper: no SL/TP stored per position in ledger.",
            }
        )

    lab = execute(
        """SELECT * FROM lab_positions WHERE symbol=%s AND account_id='lab_auto'""",
        (symbol,),
    ).fetchone()
    if lab and _f(lab["qty"]):
        qty = float(lab["qty"])
        entry = _f(lab.get("entry_price"))
        if entry is None and _f(lab.get("cost")) and qty:
            entry = float(lab["cost"]) / qty
        sl_pct = _f(lab.get("stop_loss_pct")) or 0.02
        tp_pct = _f(lab.get("take_profit_pct")) or 0.04
        max_bars = int(lab.get("max_hold_bars") or 48)
        opened_ms = lab.get("opened_candle_ms")
        # Lab INTERVAL_MS is 1h for strategy; remaining bars are informational
        from .lab.config import INTERVAL_MS

        bars_remaining = None
        if opened_ms is not None:
            held = max(0, int((now_ms - int(opened_ms)) // INTERVAL_MS))
            bars_remaining = max(0, max_bars - held)
        sl = entry * (1 - sl_pct) if entry else None
        tp = entry * (1 + tp_pct) if entry else None
        mark = mark_price
        upnl = (mark - entry) * qty if mark is not None and entry is not None else None
        overlays.append(
            {
                "ledger": "lab",
                "symbol": symbol,
                "qty": qty,
                "entry_price": entry,
                "mark_price": mark,
                "unrealized_pnl": upnl,
                "stop_loss_price": sl,
                "take_profit_price": tp,
                "stop_loss_pct": sl_pct,
                "take_profit_pct": tp_pct,
                "opened_at": _iso(lab.get("opened_at")),
                "opened_candle_ms": int(opened_ms) if opened_ms is not None else None,
                "bars_remaining": bars_remaining,
                "max_hold_bars": max_bars,
                "note": "Lab virtual SL/TP from lab_positions percentages.",
            }
        )

    return overlays
