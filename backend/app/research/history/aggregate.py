"""Agregación reproducible de temporalidades desde 1m (solo velas cerradas)."""
from __future__ import annotations

from typing import Any

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}


def floor_bucket(open_time_ms: int, interval_ms: int) -> int:
    return (open_time_ms // interval_ms) * interval_ms


def aggregate_bars(rows_1m: list[dict[str, Any]], interval: str) -> list[dict[str, Any]]:
    """Agrega 1m → interval. Solo emite buckets completos (cerrados).

    Un bucket se considera cerrado si contiene exactamente `interval_ms/60000` minutos
    o si el siguiente minuto supera el final del bucket (para huecos: no fabricamos;
    emitimos solo si hay al menos 1 barra y el bucket no es el último incompleto
    cuando conocemos el fin). Política Etapa W: emitir bucket solo si `n_expected`
    barras presentes; si hay huecos internos, aún se emite con las barras existentes
    pero se marca `incomplete=True` y `is_closed=True` solo si el último open_time
    del bucket + 1m alcanza el borde (i.e. tenemos la última vela del bucket).
    """
    if interval == "1m":
        return [
            {
                **r,
                "is_closed": True,
                "incomplete": False,
            }
            for r in rows_1m
        ]
    interval_ms = INTERVAL_MS[interval]
    n_expected = interval_ms // 60_000
    buckets: dict[int, list[dict[str, Any]]] = {}
    for r in rows_1m:
        t = int(r["open_time"])
        b = floor_bucket(t, interval_ms)
        buckets.setdefault(b, []).append(r)

    out: list[dict[str, Any]] = []
    for b in sorted(buckets):
        xs = sorted(buckets[b], key=lambda z: int(z["open_time"]))
        last_t = int(xs[-1]["open_time"])
        # cerrado solo si la última vela 1m del bucket está presente
        closed = last_t == b + interval_ms - 60_000
        incomplete = len(xs) < n_expected
        if not closed:
            # no usar bucket incompleto al final / con hueco final
            continue
        out.append(
            {
                "open_time": b,
                "open": float(xs[0]["open"]),
                "high": max(float(x["high"]) for x in xs),
                "low": min(float(x["low"]) for x in xs),
                "close": float(xs[-1]["close"]),
                "volume": sum(float(x["volume"]) for x in xs),
                "is_closed": True,
                "incomplete": incomplete,
                "n_source": len(xs),
            }
        )
    return out
