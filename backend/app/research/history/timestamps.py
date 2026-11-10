"""Normalización de timestamps Binance Vision (ms vs µs)."""
from __future__ import annotations


def normalize_open_time_ms(value: int | float | str) -> int:
    """Convierte open_time a milisegundos UTC epoch.

    Binance Vision: archivos antiguos pueden usar microsegundos.
    Heurística: >= 1e14 → microsegundos; >= 1e11 → milisegundos; else segundos.
    """
    v = int(float(value))
    if v >= 10**14:
        return v // 1000
    if v >= 10**11:
        return v
    return v * 1000


def is_aligned_1m(open_time_ms: int) -> bool:
    return open_time_ms % 60_000 == 0
