"""Hipótesis Etapa U — congeladas antes de evaluación OOS. No modifican A ni B."""
from __future__ import annotations

from typing import Any

# Versiones congeladas — no retocar tras ver resultados del mismo window
HYPOTHESES: list[dict[str, Any]] = [
    {
        "id": "U1_TREND15",
        "version": "u1_trend15_v20261110",
        "title": "Tendencia confirmada en 15 minutos",
        "human": (
            "Solo comprar si la tendencia de 15 minutos también es alcista, "
            "además de las reglas de corto plazo. Busca menos ruido de 1 minuto."
        ),
        "changes": ["Requiere EMA9>EMA21 en marco 15m agregado"],
        "frozen": True,
        "status": "research",
    },
    {
        "id": "U2_PULLBACK",
        "version": "u2_pullback_v20261110",
        "title": "Entrada tras retroceso",
        "human": (
            "Espera un pequeño retroceso hacia la media en tendencia alcista de 5m, "
            "en lugar de comprar en pleno impulso."
        ),
        "changes": ["Compra si tendencia 5m OK y precio cerca de EMA21 1m (pullback)"],
        "frozen": True,
        "status": "research",
    },
    {
        "id": "U3_ATR_EXITS",
        "version": "u3_atr_exits_v20261110",
        "title": "Salidas adaptadas al ATR",
        "human": (
            "Stop y objetivo proporcionales a la volatilidad (ATR), "
            "para no salir demasiado pronto en mercados ruidosos."
        ),
        "changes": ["SL = 1.5×ATR%", "TP = 2.5×ATR%", "mín SL 0.6%", "máx SL 2.0%"],
        "frozen": True,
        "status": "research",
    },
    {
        "id": "U4_COOLDOWN",
        "version": "u4_cooldown_v20261110",
        "title": "Menos operaciones repetitivas",
        "human": (
            "Aumenta el descanso entre compras del mismo mercado y limita "
            "entradas por hora para evitar series de micro-pérdidas."
        ),
        "changes": ["Cooldownoldown 45 min/símbolo", "Máx 2 entradas/hora globales"],
        "frozen": True,
        "status": "research",
    },
]


def list_hypotheses() -> list[dict[str, Any]]:
    return list(HYPOTHESES)
