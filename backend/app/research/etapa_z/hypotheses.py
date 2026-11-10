"""Fichas de hipótesis Z congeladas (pocas, simples, contrastables)."""
from __future__ import annotations

from typing import Any

# Parámetros congelados ANTES de OOS. No grid-search.
HYPOTHESES: dict[str, dict[str, Any]] = {
    "Z-BH-BTC": {
        "title": "Buy & hold BTC",
        "kind": "benchmark",
        "economic": "Benchmark pasivo spot BTC.",
        "rule": "100% BTC desde barra warm; hold hasta fin.",
        "tf": "1d",
        "frozen": True,
        "reject_if": "N/A benchmark",
        "advance_if": "N/A",
    },
    "Z-BH-EQ": {
        "title": "Buy & hold equiponderado",
        "kind": "benchmark",
        "economic": "Exposición 1/3 BTC+ETH+SOL rebalance diario por pesos (con costos).",
        "rule": "Pesos 1/3; rebalance diario al close.",
        "tf": "1d",
        "frozen": True,
        "reject_if": "N/A",
        "advance_if": "N/A",
    },
    "Z-TSMOM-D28H5": {
        "title": "TS momentum 28d / hold 5d (long-only)",
        "kind": "hypothesis",
        "economic": (
            "Persistencia de retornos a horizontes de semanas puede superar costos "
            "mejor que intradía corto (Moskowitz et al.; evidencia cripto mixta)."
        ),
        "new_info": "Retorno propio 28d cerrado; no usa salidas intradía A/V-BREAK.",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "tf": "1d",
        "entry": "Si retorno[t-28:t] > 0 → long; si ≤0 → cash.",
        "exit": "Reevaluación diaria; hold mínimo implícito por señal.",
        "abstain": "Retorno lookback ≤ 0.",
        "params": {"lookback": 28, "min_hold": 5},
        "frozen": True,
        "reject_if": "neto OOS ≤ BH equivalente o ≤ 0 tras costos; N insuficiente; DD > 1.5× BH",
        "advance_if": "neto OOS > max(0, BH_EQ) y coste-stress OK y adversarial sin bloqueo",
    },
    "Z-TSMOM-VOL": {
        "title": "TSMOM 28d con volatility targeting",
        "kind": "hypothesis",
        "economic": "Escalar exposición ~10% vol anualizada puede mejorar ratio riesgo/retorno.",
        "new_info": "Vol realizada 20d + señal TSMOM.",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "tf": "1d",
        "entry": "Señal TSMOM; tamaño = clip(target_vol/realized_vol, 0, 1).",
        "exit": "Igual TSMOM; tamaño se actualiza diario.",
        "params": {"lookback": 28, "vol_lb": 20, "target_vol": 0.10},
        "frozen": True,
        "reject_if": "no mejora neto vs TSMOM plano o vs cash tras costos",
        "advance_if": "mejora sharpe/neto vs Z-TSMOM-D28H5 y BH en OOS",
    },
    "Z-RS-TOP1": {
        "title": "Rotación fortaleza relativa top-1",
        "kind": "hypothesis",
        "economic": "Momentum relativo puede concentrar exposición en el activo más fuerte.",
        "new_info": "Ranking 30d entre 3 activos (universo pequeño — no generalizable).",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "tf": "1d",
        "entry": "Cada 7d: comprar el de mayor retorno 30d si >0; si todos ≤0 → cash.",
        "exit": "Al siguiente rebalance.",
        "params": {"lookback": 30, "rebalance_every": 7},
        "frozen": True,
        "warning": "Universo N=3 → sesgo y baja diversificación",
        "reject_if": "neto ≤ BH-EQ o dependencia de 1 activo; costos de rotación altos",
        "advance_if": "supera BH-EQ en OOS con DD acotado",
    },
    "Z-4H-MOM12": {
        "title": "Momentum 4h (12 barras ≈ 48h)",
        "kind": "hypothesis",
        "economic": "Horizonte intermedio entre intradía y diario.",
        "new_info": "Señal en 4h cerrada.",
        "universe": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "tf": "4h",
        "entry": "retorno 12 barras > 0 → long equal-weight; else cash.",
        "exit": "reevaluación cada barra 4h",
        "params": {"lookback": 12},
        "frozen": True,
        "reject_if": "neto ≤ 0 OOS o peor que diario TSMOM",
        "advance_if": "edge neto robusto tras costos",
    },
}


def list_hypotheses() -> list[dict[str, Any]]:
    return [{"id": k, **v} for k, v in HYPOTHESES.items()]
