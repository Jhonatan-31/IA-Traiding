"""Document and lock Lab cycle counter semantics (PAPER visualization / ops clarity)."""
from __future__ import annotations


def test_counter_meanings_are_distinct():
    """
    signals_buy  = BUY decisions detected this cycle (includes repeats on same candle)
    signals      = newly inserted rows in lab_signals (created=True)
    enqueued     = newly inserted lab_orders
    duplicates   = idempotent skips (signal and/or order already exists)
    """
    # Simulated cycle: golden cross re-seen on already-filled SOL candle
    summary = {
        "signals": 0,
        "signals_buy": 1,
        "enqueued": 0,
        "duplicates_signal": 1,
        "duplicates_order": 1,
        "duplicates": 2,
    }
    assert summary["signals_buy"] == 1
    assert summary["signals"] == 0  # no new signal row
    assert summary["enqueued"] == 0  # no new order
    assert summary["duplicates"] == (
        summary["duplicates_signal"] + summary["duplicates_order"]
    )
    # Not a contradiction: detections != inserts


def test_idempotency_keys():
    signal_key = ("SMA10_SMA50_1H", "SOLUSDT", "BUY", 1793739600000)
    order_key = ("lab_auto", "SMA10_SMA50_1H", "SOLUSDT", "BUY", 1793739600000)
    assert len(signal_key) == 4
    assert len(order_key) == 5
