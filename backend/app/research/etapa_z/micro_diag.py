"""Z4/Z5 — diagnóstico de datos de microestructura y derivados (sin cargas masivas)."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Any

from . import INITIAL_CAPITAL


def diagnose_microstructure() -> dict[str, Any]:
    """Qué existe hoy vs qué faltaría para señales de flujo/libro."""
    disk = shutil.disk_usage("/")
    return {
        "fase": "Z4",
        "available_now": {
            "spot_ohlcv_1m_parquet": True,
            "taker_buy_in_parquet": False,
            "public_trades_history": False,
            "order_book_snapshots": False,
            "bbo_history": False,
        },
        "vision_klines_note": (
            "Los CSV de Binance Vision klines incluyen taker_buy_base/quote, "
            "pero el store Parquet actual solo persiste OHLCV. "
            "No inventamos profundidad desde OHLCV."
        ),
        "to_enable_ofi_smoke": {
            "action": "re-ingestar klines con columnas taker_buy O descargar 1 día de aggTrades",
            "estimated_aggtrades_1day_btc_mb": "50–200 (variable)",
            "disk_free_gb": round(disk.free / 1e9, 2),
            "policy": "no descarga masiva en esta etapa sin aprobación de tamaño",
        },
        "streaming_only": ["bookTicker live", "depth live — requiere grabación prospectiva"],
        "verdict": "insufficient_for_micro_edge_claim",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def diagnose_derivatives() -> dict[str, Any]:
    return {
        "fase": "Z5",
        "spot_execution_only": True,
        "leverage_enabled": False,
        "sources": {
            "funding_rate_vision": {
                "available": True,
                "path_pattern": "data/futures/um/monthly/fundingRate/{SYMBOL}/",
                "ingested": False,
                "latency_note": "archivo mensual ~2 días después; no usar como si fuera live",
            },
            "open_interest_vision_metrics": {
                "available": True,
                "path_pattern": "data/futures/um/daily/metrics/",
                "ingested": False,
                "size_warning": "métricas 5m diarias — estimar antes de bajar 12m×3 símbolos",
            },
            "open_interest_rest": {
                "available": "últimos ~30 días",
                "insufficient_for_2024_2025_panel": True,
            },
        },
        "hypotheses_not_tested_here": [
            "funding alto → short spot (no probado: sin serie ingestada)",
            "ΔOI + precio → breakout (no probado)",
        ],
        "verdict": "informative_source_possible_after_controlled_ingest",
        "capital_ref": INITIAL_CAPITAL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
