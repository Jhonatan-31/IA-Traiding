"""Trade→candle aggregation + normalize — visualization only."""
from __future__ import annotations

from app.market_stream.aggregator import CandleAggregator, candle_open_ms
from app.market_stream.normalize import normalize_trade_message, trade_stream_name


def _trade(tid: int, price: float, qty: float, t_ms: int, e_ms: int | None = None):
    return {
        "type": "trade",
        "symbol": "BTCUSDT",
        "price": price,
        "qty": qty,
        "trade_id": tid,
        "event_time_ms": e_ms if e_ms is not None else t_ms,
        "trade_time_ms": t_ms,
        "kind": "trade",
        "source": "t",
    }


def test_trade_stream_name():
    assert trade_stream_name("BTCUSDT") == "btcusdt@trade"


def test_normalize_trade():
    raw = {
        "stream": "btcusdt@trade",
        "data": {
            "e": "trade",
            "E": 1000,
            "s": "BTCUSDT",
            "t": 55,
            "p": "100.5",
            "q": "0.01",
            "T": 999,
            "m": False,
        },
    }
    msg = normalize_trade_message(raw)
    assert msg is not None
    assert msg["price"] == 100.5
    assert msg["qty"] == 0.01
    assert msg["trade_id"] == 55
    assert msg["trade_time_ms"] == 999


def test_volume_sum_and_dedupe():
    agg = CandleAggregator()
    t0 = 1_700_000_000_000
    open_ms = candle_open_ms(t0, "1m")
    c1 = agg.apply_trade(_trade(1, 100, 1.0, open_ms + 100), "1m")
    assert c1 is not None and c1.volume == 1.0
    c2 = agg.apply_trade(_trade(2, 105, 0.5, open_ms + 200), "1m")
    assert c2 is not None
    assert c2.high == 105 and c2.low == 100 and c2.close == 105
    assert abs(c2.volume - 1.5) < 1e-9
    assert agg.apply_trade(_trade(2, 105, 0.5, open_ms + 200), "1m") is None  # dup id


def test_out_of_order_older_id_rejected():
    agg = CandleAggregator()
    t0 = 1_700_000_060_000
    assert agg.apply_trade(_trade(10, 100, 1, t0), "1m")
    assert agg.apply_trade(_trade(9, 99, 1, t0 + 1), "1m") is None


def test_new_candle_on_interval():
    agg = CandleAggregator()
    step = 60_000
    t0 = candle_open_ms(1_700_000_000_000, "1m")
    assert agg.apply_trade(_trade(1, 100, 1, t0 + 1), "1m")
    nxt = t0 + step
    c = agg.apply_trade(_trade(2, 110, 2, nxt + 1), "1m")
    assert c is not None
    assert c.candle_open_ms == nxt
    assert c.open == 110 and c.volume == 2


def test_kline_reconcile_closed_authoritative():
    agg = CandleAggregator()
    t0 = 1_700_000_000_000
    agg.apply_trade(_trade(1, 100, 1, t0 + 10), "1m")
    closed = agg.apply_kline(
        {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "candle_open_ms": t0,
            "event_time_ms": t0 + 59_999,
            "open": 99,
            "high": 120,
            "low": 90,
            "close": 115,
            "volume": 50,
            "is_closed": True,
        }
    )
    assert closed is not None
    assert closed.is_closed
    assert closed.open == 99 and closed.close == 115 and closed.volume == 50
    # trades must not mutate closed
    assert agg.apply_trade(_trade(99, 200, 1, t0 + 30), "1m") is None


def test_stale_open_rejected():
    agg = CandleAggregator()
    t0 = 1_700_000_120_000
    agg.apply_trade(_trade(1, 100, 1, t0), "1m")
    assert agg.apply_trade(_trade(2, 90, 1, t0 - 60_000), "1m") is None
