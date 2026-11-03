"""Research strategies with explicit entry/exit/abstain — never auto-activated live."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..indicators import sma
from .labels import HORIZON


@dataclass(frozen=True)
class StrategySpec:
    name: str
    entry: str
    exit: str
    horizon_bars: int
    max_positions: int
    fee_rate: float
    slip_rate: float
    abstain_when: str
    risk_limits: dict[str, Any]
    auto_activate: bool = False  # always False in Etapa G


SPECS: dict[str, StrategySpec] = {
    "cash": StrategySpec(
        name="cash",
        entry="never",
        exit="n/a",
        horizon_bars=HORIZON,
        max_positions=0,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="always",
        risk_limits={"max_exposure_pct": 0},
    ),
    "buy_hold": StrategySpec(
        name="buy_hold",
        entry="always long each bar (research only)",
        exit=f"close after {HORIZON} bars",
        horizon_bars=HORIZON,
        max_positions=10,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="never",
        risk_limits={"max_exposure_pct": 100},
    ),
    "sma10_50": StrategySpec(
        name="sma10_50",
        entry="SMA10 > SMA50 on closed bar t",
        exit=f"horizon {HORIZON} or cross down",
        horizon_bars=HORIZON,
        max_positions=10,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="SMA incomplete",
        risk_limits={"max_exposure_pct": 80},
    ),
    "momentum_vol_filter": StrategySpec(
        name="momentum_vol_filter",
        entry="momentum_10 > 0 and realized_vol_20 below median",
        exit=f"horizon {HORIZON}",
        horizon_bars=HORIZON,
        max_positions=5,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="high vol or weak momentum",
        risk_limits={"max_exposure_pct": 50},
    ),
    "mean_reversion": StrategySpec(
        name="mean_reversion",
        entry="close < SMA20 - k*ATR and RSI < 35",
        exit=f"horizon {HORIZON}",
        horizon_bars=HORIZON,
        max_positions=5,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="insufficient history or strong downtrend SMA50",
        risk_limits={"max_exposure_pct": 40},
    ),
    "trend_volume": StrategySpec(
        name="trend_volume",
        entry="SMA20>SMA50 and volume > 1.2*vol_ma20",
        exit=f"horizon {HORIZON}",
        horizon_bars=HORIZON,
        max_positions=5,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="volume confirmation missing",
        risk_limits={"max_exposure_pct": 50},
    ),
    "breakout_liquidity": StrategySpec(
        name="breakout_liquidity",
        entry="close > max(high[-20:-1]) and vol_ma20 high",
        exit=f"horizon {HORIZON}",
        horizon_bars=HORIZON,
        max_positions=3,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="low liquidity proxy",
        risk_limits={"max_exposure_pct": 40},
    ),
    "hgb_calibrated_abstain": StrategySpec(
        name="hgb_calibrated_abstain",
        entry="calibrated_proba >= 0.60 AND expected_net > 0",
        exit=f"horizon {HORIZON}",
        horizon_bars=HORIZON,
        max_positions=5,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="proba in [0.45,0.60) or E[net]<=0",
        risk_limits={"max_exposure_pct": 50},
    ),
    "logistic_calibrated_abstain": StrategySpec(
        name="logistic_calibrated_abstain",
        entry="calibrated_proba >= 0.58 AND expected_net > 0",
        exit=f"horizon {HORIZON}",
        horizon_bars=HORIZON,
        max_positions=5,
        fee_rate=0.001,
        slip_rate=0.001,
        abstain_when="uncertain probability band",
        risk_limits={"max_exposure_pct": 50},
    ),
}


def signal_sma10_50(closes: list[float]) -> list[int]:
    f = sma(closes, 10)
    s = sma(closes, 50)
    out = [0] * len(closes)
    for i in range(len(closes)):
        if f[i] is None or s[i] is None:
            out[i] = 0
        else:
            out[i] = 1 if f[i] > s[i] else 0  # type: ignore
    return out


def signal_momentum_vol(candles: list[dict]) -> list[int]:
    closes = [float(c["close"]) for c in candles]
    n = len(closes)
    out = [0] * n
    # realized vol series
    rvol = [None] * n
    for i in range(20, n):
        import math

        rets = [
            math.log(closes[j] / closes[j - 1])
            for j in range(i - 19, i + 1)
            if closes[j - 1] > 0
        ]
        if len(rets) == 20:
            m = sum(rets) / 20
            rvol[i] = (sum((x - m) ** 2 for x in rets) / 20) ** 0.5
    # median of available rvol up to i (causal)
    hist: list[float] = []
    for i in range(n):
        if rvol[i] is not None:
            hist.append(float(rvol[i]))
        if i < 20 or rvol[i] is None:
            continue
        med = sorted(hist)[len(hist) // 2]
        mom = closes[i] / closes[i - 10] - 1 if i >= 10 and closes[i - 10] > 0 else 0
        out[i] = 1 if mom > 0 and float(rvol[i]) <= med else 0
    return out


def signal_mean_reversion(candles: list[dict]) -> list[int]:
    from ..indicators import atr, rsi

    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    a = atr(highs, lows, closes, 14)
    r = rsi(closes, 14)
    out = [0] * len(closes)
    for i in range(len(closes)):
        if None in (s20[i], s50[i], a[i], r[i]):
            continue
        # abstain in strong downtrend
        if closes[i] < s50[i]:  # type: ignore
            continue
        if closes[i] < s20[i] - 1.0 * a[i] and r[i] < 35:  # type: ignore
            out[i] = 1
    return out


def signal_trend_volume(candles: list[dict]) -> list[int]:
    closes = [float(c["close"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]
    s20 = sma(closes, 20)
    s50 = sma(closes, 50)
    vma = sma(vols, 20)
    out = [0] * len(closes)
    for i in range(len(closes)):
        if None in (s20[i], s50[i], vma[i]):
            continue
        if s20[i] > s50[i] and vma[i] and vols[i] > 1.2 * vma[i]:  # type: ignore
            out[i] = 1
    return out


def signal_breakout_liquidity(candles: list[dict]) -> list[int]:
    highs = [float(c["high"]) for c in candles]
    closes = [float(c["close"]) for c in candles]
    vols = [float(c["volume"]) for c in candles]
    vma = sma(vols, 20)
    out = [0] * len(closes)
    for i in range(len(closes)):
        if i < 21 or vma[i] is None:
            continue
        prior_high = max(highs[i - 20 : i])
        # liquidity proxy: vol ma above its own recent median
        window = [vma[j] for j in range(i - 20, i + 1) if vma[j] is not None]
        if not window:
            continue
        med = sorted(window)[len(window) // 2]
        if closes[i] > prior_high and vma[i] >= med:  # type: ignore
            out[i] = 1
    return out


def signal_from_proba(
    proba: list[float | None],
    *,
    threshold: float,
    expected_net: list[float | None] | None = None,
) -> list[int]:
    out = [0] * len(proba)
    for i, p in enumerate(proba):
        if p is None:
            continue
        en = expected_net[i] if expected_net else 0.0
        if expected_net is not None and (en is None or en <= 0):
            continue
        if p >= threshold:
            out[i] = 1
    return out


def list_strategy_specs() -> list[dict[str, Any]]:
    return [asdict(s) for s in SPECS.values()]
