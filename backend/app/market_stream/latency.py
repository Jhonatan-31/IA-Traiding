"""Latency helpers — never mix distinct monotonic clocks across hosts."""
from __future__ import annotations

from typing import Any


def percentile(samples: list[float], p: float) -> float | None:
    if not samples:
        return None
    xs = sorted(samples)
    if len(xs) == 1:
        return xs[0]
    # nearest-rank
    idx = min(len(xs) - 1, max(0, int(round((p / 100.0) * (len(xs) - 1)))))
    return float(xs[idx])


def summarize(samples: list[float], *, note: str) -> dict[str, Any]:
    return {
        "n": len(samples),
        "p50": percentile(samples, 50),
        "p95": percentile(samples, 95),
        "p99": percentile(samples, 99),
        "note": note,
    }


def wall_delta_ms(later_ms: int | float, earlier_ms: int | float) -> float | None:
    """Wall-clock delta; reject negatives (skew / reordering)."""
    d = float(later_ms) - float(earlier_ms)
    if d < 0:
        return None
    return d


def mono_delta_ms(later_mono: float, earlier_mono: float) -> float | None:
    """Monotonic delta on the SAME host; reject negatives."""
    d = (float(later_mono) - float(earlier_mono)) * 1000.0
    if d < 0:
        return None
    return d


class LatencyTracker:
    def __init__(self, maxlen: int = 500) -> None:
        self.maxlen = maxlen
        self.binance_to_hub: list[float] = []
        self.hub_internal: list[float] = []
        self.negative_binance_hub = 0

    def push_binance_to_hub(self, value: float | None) -> None:
        if value is None:
            self.negative_binance_hub += 1
            return
        self.binance_to_hub.append(float(value))
        if len(self.binance_to_hub) > self.maxlen:
            self.binance_to_hub = self.binance_to_hub[-self.maxlen :]

    def push_hub_internal(self, value: float | None) -> None:
        if value is None:
            return
        self.hub_internal.append(float(value))
        if len(self.hub_internal) > self.maxlen:
            self.hub_internal = self.hub_internal[-self.maxlen :]

    def snapshot(self) -> dict[str, Any]:
        b = summarize(
            self.binance_to_hub,
            note="wall-clock event->hub_recv; includes NTP/clock skew; negatives discarded",
        )
        h = summarize(
            self.hub_internal,
            note="monotonic hub_recv->emit (includes coalesce); same process only",
        )
        ewma = None
        if self.binance_to_hub:
            ewma = self.binance_to_hub[0]
            for x in self.binance_to_hub[1:]:
                ewma = 0.85 * float(ewma) + 0.15 * x
        return {
            "binance_to_hub_ms": b,
            "hub_internal_ms": h,
            "binance_to_hub_ewma_ms": ewma,
            "negatives_discarded": self.negative_binance_hub,
        }
