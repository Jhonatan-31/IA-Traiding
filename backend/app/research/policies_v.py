"""Políticas Etapa V — versionadas y congeladas ANTES de evaluar OOS.

No modifican A/B. No martingala. Stop obligatorio. Exposición acotada.
"""
from __future__ import annotations

from typing import Any

FEE_RATE = 0.001  # taker 10 bps (Binance spot retail approx; documentado)
SLIP_RATE = 0.0005
MAX_POS_USDT = 25.0
MAX_POSITIONS = 3
MAX_EXPOSURE_USDT = 75.0

POLICIES: dict[str, dict[str, Any]] = {
    "A_BASELINE": {
        "id": "A_BASELINE",
        "version": "demo_policy_v1_20261103",
        "title": "Conservadora (baseline)",
        "status": "baseline_immutable",
        "human": "Política Demo 4/5 congelada. Solo referencia; no se modifica.",
        "frozen": True,
    },
    "B_BASELINE": {
        "id": "B_BASELINE",
        "version": "active_policy_b_v1_20261104",
        "title": "Trading Activo (baseline B)",
        "status": "baseline_immutable",
        "human": "Cruce EMA + filtros de costo. Referencia; no se modifica en Etapa V.",
        "frozen": True,
    },
    "V_TREND": {
        "id": "V_TREND",
        "version": "v_trend_pullback_v20261110",
        "title": "Tendencia con retroceso",
        "status": "research",
        "frozen": True,
        "human": (
            "Tendencia alcista en 1h (EMA20>EMA50). Entrada en retroceso 15m hacia EMA21 "
            "con RSI 40–55 y volumen ≥ SMA20. SL −1.2%, TP +2.4% o invalidación EMA20 1h."
        ),
        "rules": {
            "htf": "1h_agg_from_1m",
            "htf_trend": "ema20 > ema50",
            "entry_tf": "15m_agg",
            "entry": "close within 0.35% of ema21 AND 40<=rsi14<=55 AND vol>=sma20_vol",
            "stop_loss_pct": 0.012,
            "take_profit_pct": 0.024,
            "invalidation": "ema20_1h < ema50_1h",
            "cooldown_bars_1m": 60,
            "max_pos_usdt": MAX_POS_USDT,
            "max_positions": MAX_POSITIONS,
            "fee": FEE_RATE,
            "slip": SLIP_RATE,
        },
    },
    "V_BREAK": {
        "id": "V_BREAK",
        "version": "v_breakout_v20261110",
        "title": "Ruptura de rango",
        "status": "research",
        "frozen": True,
        "human": (
            "Rango 15m de 12 barras; ruptura alcista de máximo con volumen > 1.2×SMA. "
            "Entrada en close de confirmación. SL bajo el rango, TP 1.5×altura del rango (cap 3%)."
        ),
        "rules": {
            "range_bars_15m": 12,
            "break_confirm": "close > range_high AND vol > 1.2*sma20_vol",
            "stop": "range_low (floored to max 2% below entry)",
            "take": "entry + 1.5*(range_high-range_low) capped at +3%",
            "false_break_filter": "reject if atr_pct < 1.2*(fee+slip)",
            "cooldown_bars_1m": 90,
            "max_pos_usdt": MAX_POS_USDT,
            "fee": FEE_RATE,
            "slip": SLIP_RATE,
        },
    },
    "V_MEAN": {
        "id": "V_MEAN",
        "version": "v_mean_revert_v20261110",
        "title": "Reversión a la media (secundaria)",
        "status": "research_secondary",
        "frozen": True,
        "human": (
            "Solo en régimen lateral + baja volatilidad. RSI<30 con precio bajo banda. "
            "Una sola entrada por símbolo. SL estricto −0.8%. Sin martingala ni promediar."
        ),
        "rules": {
            "regime_required": "sideways|low_volatility OR sideways|normal_volatility",
            "entry": "rsi14<30 AND close < ema21*0.995",
            "stop_loss_pct": 0.008,
            "take_profit_pct": 0.012,
            "max_adds": 0,
            "martingale": False,
            "fee": FEE_RATE,
            "slip": SLIP_RATE,
        },
    },
    "V_IA": {
        "id": "V_IA",
        "version": "v_ia_observe_v20261110",
        "title": "Clasificación experimental IA",
        "status": "observation_only",
        "frozen": True,
        "human": "Solo auditoría de predicciones Shadow. Ejecución prohibida sin calibración y OOS.",
        "execution_authorized": False,
    },
}


def list_policies() -> list[dict[str, Any]]:
    return list(POLICIES.values())
