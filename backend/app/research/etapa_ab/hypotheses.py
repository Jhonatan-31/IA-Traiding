"""AB5 — hipótesis exploratorias de preservación (NO ejecutadas, NO optimizadas en holdout)."""
from __future__ import annotations

from typing import Any

# Parámetros prerregistrados para futuros experimentos (fuera del holdout AA).
EXPLORATORY_HYPOTHESES: list[dict[str, Any]] = [
    {
        "id": "AB-H1-CASH-ADVERSE",
        "title": "Efectivo en régimen adverso",
        "economic": "Reducir exposición cuando retorno 60d del EQ < 0",
        "params_preregistered": {"lookback_days": 60, "threshold": 0.0},
        "status": "registered_not_run",
        "forbidden": "no optimizar en holdout AA",
    },
    {
        "id": "AB-H2-VOL-TARGET",
        "title": "Exposición por volatilidad",
        "economic": "Escalar a target_vol 25% ann con vol 20d pasada",
        "params_preregistered": {"vol_lb": 20, "target_vol": 0.25},
        "status": "registered_not_run",
        "forbidden": "no combinar con H1/H3 en el mismo experimento sin protocolo",
    },
    {
        "id": "AB-H3-REBAL-BAND",
        "title": "Bandas de rebalanceo",
        "economic": "Solo rebalancear si |w_tgt-w_act| > 5pp por activo",
        "params_preregistered": {"band": 0.05, "min_delta_usdt": 25.0},
        "status": "registered_not_run",
        "note": "Orienta a reducir los ~72 USDT de fricción de D28H5",
    },
]


def list_hypotheses() -> dict[str, Any]:
    return {
        "n": len(EXPLORATORY_HYPOTHESES),
        "items": EXPLORATORY_HYPOTHESES,
        "d28h5_unchanged": True,
        "warning": "Exploratorias ≠ promoción. Separadas de la versión congelada.",
    }
