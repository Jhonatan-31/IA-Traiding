"""Etapa W — historial Vision: timestamps, OHLC, agregación, aislamiento."""
from __future__ import annotations

from app.research.history.aggregate import aggregate_bars, floor_bucket
from app.research.history.download import parse_checksum_body, parse_klines_csv
from app.research.history.timestamps import normalize_open_time_ms
from app.research.history.validate import validate_rows


def test_normalize_timestamps_ms_us_s():
    assert normalize_open_time_ms(1_700_000_000_000) == 1_700_000_000_000  # ms
    assert normalize_open_time_ms(1_700_000_000_000_000) == 1_700_000_000_000  # µs → ms
    assert normalize_open_time_ms(1_700_000_000) == 1_700_000_000_000  # s → ms


def test_parse_checksum_and_csv():
    assert parse_checksum_body("abc123  file.zip\n") == "abc123"
    raw = b"\n".join(
        [
            b"open_time,open,high,low,close,volume,x",
            b"1700000000000,100,101,99,100.5,12,0",
            b"1700000060000,100.5,102,100,101,10,0",
        ]
    )
    rows = parse_klines_csv(raw)
    assert len(rows) == 2
    assert rows[0]["open"] == 100.0


def test_validate_ohlc_gaps_dedupe_no_fill():
    base = 1_700_000_000_000
    rows = [
        {"open_time": base, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},
        {"open_time": base, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1},  # dup
        {"open_time": base + 120_000, "open": 100, "high": 101, "low": 99, "close": 100.2, "volume": 1},  # gap
    ]
    rep = validate_rows(rows)
    assert rep["duplicates"] == 1
    assert rep["gap_count"] >= 1
    assert rep["filled_fabricated"] is False
    assert rep["n"] == 2


def test_aggregate_5m_closed_only():
    base = 1_700_000_000_000
    # align to 5m bucket
    base = floor_bucket(base, 300_000)
    rows = []
    for i in range(5):
        rows.append(
            {
                "open_time": base + i * 60_000,
                "open": 100 + i,
                "high": 110,
                "low": 90,
                "close": 100 + i + 0.5,
                "volume": 1.0,
            }
        )
    # incomplete next bucket (2 bars) must not emit
    for i in range(2):
        rows.append(
            {
                "open_time": base + 300_000 + i * 60_000,
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 1.0,
            }
        )
    out = aggregate_bars(rows, "5m")
    assert len(out) == 1
    assert out[0]["open_time"] == base
    assert out[0]["is_closed"] is True
    assert out[0]["open"] == 100
    assert out[0]["close"] == 104.5


def test_policies_still_frozen_no_execution():
    from app.research.policies_v import POLICIES

    assert POLICIES["V_TREND"]["frozen"] is True
    assert POLICIES["V_IA"]["execution_authorized"] is False
