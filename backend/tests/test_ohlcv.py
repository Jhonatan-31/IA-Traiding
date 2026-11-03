import pytest
from app import ohlcv


def test_validate_symbol_ok():
    assert ohlcv.validate_symbol("btcusdt") == "BTCUSDT"


def test_validate_symbol_bad():
    with pytest.raises(ValueError):
        ohlcv.validate_symbol("btc")


def test_validate_interval():
    assert ohlcv.validate_interval("1h") == "1h"
    with pytest.raises(ValueError):
        ohlcv.validate_interval("3h")


def test_validate_limit():
    assert ohlcv.validate_limit(None) == ohlcv.DEFAULT_LIMIT
    with pytest.raises(ValueError):
        ohlcv.validate_limit(5)


def test_parse_closed_vs_forming():
    now = 1_000_000
    rows = [
        [0, "1", "2", "0.5", "1.5", "10", 100, "100", 1, "0", "0", "0"],
        [200, "1.5", "3", "1", "2", "20", 2_000_000, "200", 1, "0", "0", "0"],
    ]
    candles = ohlcv._parse_klines(rows, now)
    assert candles[0]["is_closed"] is True
    assert candles[1]["is_closed"] is False


@pytest.mark.asyncio
async def test_fetch_cache_and_http_errors(monkeypatch):
    ohlcv.clear_cache()
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, status, data):
            self.status_code = status
            self._data = data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("http")

        def json(self):
            return self._data

    class FakeClient:
        async def get(self, url, params=None, timeout=None):
            calls["n"] += 1
            now_open = 1_700_000_000_000
            row = [
                now_open,
                "1",
                "2",
                "0.5",
                "1.5",
                "10",
                now_open + 3_599_999,
                "100",
                1,
                "0",
                "0",
                "0",
            ]
            return FakeResp(200, [row] * 12)

    client = FakeClient()
    a = await ohlcv.fetch_klines(client, "BTCUSDT", "1h", limit=12)
    b = await ohlcv.fetch_klines(client, "BTCUSDT", "1h", limit=12)
    assert a["cache"] == "MISS"
    assert b["cache"] == "HIT"
    assert calls["n"] == 1
    assert ohlcv.cache_stats()["hits"] >= 1

    class BadClient:
        async def get(self, url, params=None, timeout=None):
            return FakeResp(429, {})

    ohlcv.clear_cache()
    with pytest.raises(RuntimeError):
        await ohlcv.fetch_klines(BadClient(), "BTCUSDT", "1h", limit=12, use_cache=False)
