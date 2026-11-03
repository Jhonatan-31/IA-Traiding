"""Chart overlay markers/positions — visualization only, no orders."""
from __future__ import annotations

from datetime import datetime, timezone
from app.chart_overlay import build_open_position_overlays, build_trade_markers


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


def test_build_markers_separates_ledgers_and_predictions():
    calls = []

    def execute(sql, params=None):
        calls.append(sql)
        s = sql.lower()
        if "from trades" in s:
            return FakeCursor(
                [
                    {
                        "id": 1,
                        "at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                        "side": "BUY",
                        "qty": 0.1,
                        "price": 100,
                        "candle_ms": 1000,
                        "strategy": "SMA",
                        "reason": "cross",
                    }
                ]
            )
        if "from lab_trades" in s:
            return FakeCursor(
                [
                    {
                        "id": 2,
                        "at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                        "side": "SELL",
                        "qty": 0.1,
                        "price": 110,
                        "candle_ms": 2000,
                        "strategy": "LAB",
                        "reason": "tp",
                    }
                ]
            )
        if "from prospect_decisions" in s:
            return FakeCursor(
                [
                    {
                        "id": 3,
                        "created_at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                        "action": "BUY",
                        "strategy": "prospect",
                        "reason": "signal",
                        "candle_open_ms": 3000,
                        "observed_price": 105,
                        "interval": "1h",
                    }
                ]
            )
        if "from ml_predictions" in s:
            return FakeCursor(
                [
                    {
                        "id": 4,
                        "created_at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                        "proposed_action": "BUY_CANDIDATE",
                        "probability": 0.7,
                        "candle_open_ms": 4000,
                        "interval": "1h",
                        "model_version": "v1",
                    }
                ]
            )
        return FakeCursor([])

    markers = build_trade_markers(execute, "btcusdt")
    ledgers = {m["ledger"] for m in markers}
    assert ledgers == {"sma", "lab", "shadow"}
    preds = [m for m in markers if m["kind"] == "prediction"]
    assert len(preds) == 2
    assert all(m["kind"] == "prediction" for m in preds)
    assert all("PRED" in m["label"] or "SH" in m["label"] for m in preds)
    execs = [m for m in markers if m["kind"] == "execution"]
    assert len(execs) == 2


def test_position_overlays_lab_sl_tp_and_sma_without():
    def execute(sql, params=None):
        s = sql.lower()
        if "from positions" in s:
            return FakeCursor([{"symbol": "BTCUSDT", "qty": 0.01, "cost": 700}])
        if "from lab_positions" in s:
            return FakeCursor(
                [
                    {
                        "account_id": "lab_auto",
                        "symbol": "BTCUSDT",
                        "qty": 0.02,
                        "cost": 25,
                        "entry_price": 78000,
                        "opened_at": datetime(2026, 11, 3, 21, tzinfo=timezone.utc),
                        "opened_candle_ms": 1_700_000_000_000,
                        "stop_loss_pct": 0.02,
                        "take_profit_pct": 0.04,
                        "max_hold_bars": 48,
                    }
                ]
            )
        return FakeCursor([])

    rows = build_open_position_overlays(execute, "BTCUSDT", mark_price=77000)
    by = {r["ledger"]: r for r in rows}
    assert "sma" in by and "lab" in by
    assert by["sma"]["stop_loss_price"] is None
    assert by["lab"]["stop_loss_price"] == 78000 * 0.98
    assert by["lab"]["take_profit_price"] == 78000 * 1.04
    assert by["lab"]["unrealized_pnl"] is not None


def test_ohlcv_end_time_param_in_signature():
    import inspect
    from app.ohlcv import fetch_klines

    sig = inspect.signature(fetch_klines)
    assert "end_time" in sig.parameters
