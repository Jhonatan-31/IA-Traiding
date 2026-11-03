"""Client-side WS candle guards (mirrors frontend candleState helpers)."""
from __future__ import annotations


def should_apply_live(last_open, last_event, msg: dict) -> bool:
    open_ms = msg["candle_open_ms"]
    event_ms = msg.get("event_time_ms", open_ms)
    if last_open is not None and open_ms < last_open:
        return False
    if last_open == open_ms and last_event is not None and event_ms < last_event:
        return False
    return True


def merge_candles(existing, incoming, mode="prepend"):
    base = [] if mode == "replace" else list(existing)
    m = {c["open_time"]: c for c in base}
    for c in incoming:
        m[c["open_time"]] = c
    return sorted(m.values(), key=lambda x: x["open_time"])


def test_reject_duplicate_older_event():
    base = {"candle_open_ms": 1000, "event_time_ms": 1100}
    assert not should_apply_live(1000, 1200, base)
    assert should_apply_live(1000, 1100, {**base, "event_time_ms": 1150})


def test_reject_out_of_order_open():
    assert not should_apply_live(2000, 2000, {"candle_open_ms": 1000, "event_time_ms": 1001})


def test_accept_new_candle_and_close():
    assert should_apply_live(1000, 1100, {"candle_open_ms": 2000, "event_time_ms": 2001})
    assert should_apply_live(
        2000, 2001, {"candle_open_ms": 2000, "event_time_ms": 2050, "is_closed": True}
    )


def test_merge_dedupes_and_orders():
    a = [{"open_time": 2, "close": 2}, {"open_time": 3, "close": 3}]
    b = [{"open_time": 1, "close": 1}, {"open_time": 2, "close": 22}]
    out = merge_candles(a, b, "prepend")
    assert [x["open_time"] for x in out] == [1, 2, 3]
    assert out[1]["close"] == 22


def test_merge_replace_clears():
    out = merge_candles(
        [{"open_time": 9, "close": 9}],
        [{"open_time": 1, "close": 1}],
        "replace",
    )
    assert [x["open_time"] for x in out] == [1]


def test_rapid_symbol_switch_resets_guards():
    """Simulate symbol change: last refs cleared → first message accepted."""
    last_open = last_event = None
    msg = {"candle_open_ms": 5000, "event_time_ms": 5001}
    assert should_apply_live(last_open, last_event, msg)
