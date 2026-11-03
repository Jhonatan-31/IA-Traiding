"""Unit tests with known vectors — no network, no production DB."""
from app.indicators import atr, bollinger, ema, macd, rsi, sma


def test_sma_warmup_and_values():
    xs = [1, 2, 3, 4, 5, 6]
    out = sma(xs, 3)
    assert out[:2] == [None, None]
    assert out[2] == 2.0
    assert out[3] == 3.0
    assert out[5] == 5.0


def test_ema_seed_is_sma():
    xs = [1, 2, 3, 4, 5]
    out = ema(xs, 3)
    assert out[0] is None and out[1] is None
    assert out[2] == 2.0  # SMA seed
    # EMA next: 4*(2/4) + 2*(2/4) = 2 + 1 = 3
    assert abs(out[3] - 3.0) < 1e-12


def test_rsi_constant_uptrend_near_100():
    xs = list(range(1, 30))
    out = rsi(xs, 14)
    assert all(v is None for v in out[:14])
    assert out[14] is not None and out[14] > 99


def test_rsi_insufficient_data():
    assert all(v is None for v in rsi([1, 2, 3], 14))


def test_macd_structure_no_lookahead_nones():
    xs = [float(i) for i in range(1, 80)]
    pack = macd(xs)
    assert pack["macd"][25] is not None  # slow period-1
    # signal needs additional warmup after macd exists
    first_sig = next(i for i, v in enumerate(pack["signal"]) if v is not None)
    assert first_sig >= 25


def test_bollinger_symmetric_on_flat():
    xs = [10.0] * 30
    bb = bollinger(xs, 20, 2)
    assert bb["middle"][19] == 10.0
    assert abs(bb["upper"][19] - 10.0) < 1e-9
    assert abs(bb["lower"][19] - 10.0) < 1e-9


def test_atr_warmup():
    h = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    l = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    c = [9.5, 10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5]
    out = atr(h, l, c, 5)
    assert all(v is None for v in out[:5])
    assert out[5] is not None and out[5] > 0
