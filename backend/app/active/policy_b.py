"""Frozen Strategy B — active crossover policy. Do not retune from live outcomes."""
from __future__ import annotations

from . import POLICY_B_VERSION, SYMBOLS

SYMBOLS_TUPLE = SYMBOLS
POLICY_VERSION = POLICY_B_VERSION
POLICY_DOC = "docs/ETAPA_T_POLICIES.md"

MAX_POS_USDT = 25.0
MAX_POSITIONS = 3
MAX_EXPOSURE_USDT = 75.0
STOP_LOSS_PCT = 0.01
TAKE_PROFIT_PCT = 0.02
PEAK_DD_PAUSE_PCT = 0.03

FEE_RATE = 0.001
SLIP_RATE = 0.0005

RSI_BUY_LO = 42.0
RSI_BUY_HI = 68.0
RSI_EXIT = 40.0
VOL_FLOOR_MULT = 0.60
ATR_PCT_MAX = 0.025
COST_ATR_MULT = 1.5  # atr must cover ~1.5× (fee+slip); avoids dead markets
COOLDOWN_SEC = 15 * 60
MAX_ENTRIES_PER_HOUR = 6

HUMAN_REASONS = {
    "ema_cross_up_active": "El bot detectó tendencia alcista con impulso fresco en 1 y 5 minutos.",
    "cost_filter_reject": "La operación fue descartada porque los costos estimados eran altos frente a la volatilidad.",
    "vol_floor_reject": "Se descartó la señal: el volumen era demasiado bajo (poca liquidez relativa).",
    "rsi_out_of_band": "El impulso (RSI) no estaba en una zona favorable para comprar.",
    "no_5m_trend": "No hay tendencia alcista clara en el marco de 5 minutos.",
    "no_ema_cross": "Aún no hay cruce alcista de medias en 1 minuto.",
    "atr_extreme": "La volatilidad es demasiado alta para esta política.",
    "cooldown": "Periodo de enfriamiento tras una operación reciente en este mercado.",
    "max_entries_hour": "Se alcanzó el límite de compras por hora.",
    "hold_position": "Ya hay una posición abierta en este mercado.",
    "stop_loss_1pct": "La posición se vendió por protección de pérdida (−1%).",
    "take_profit_2pct": "La posición se vendió por objetivo de ganancia (+2%).",
    "ema_cross_down_exit": "Se vendió: las medias en 1 minuto cruzaron a la baja.",
    "bot_stopped_entries_blocked": "El bot está detenido: no abre compras nuevas.",
    "peak_drawdown_pause": "Pausa por protección: la cuenta bajó desde su máximo.",
    "max_positions": "Ya hay el máximo de posiciones abiertas.",
    "max_exposure": "Se alcanzó el límite de dinero invertido.",
    "no_clear_signal": "Sin oportunidad clara en este ciclo.",
}


def human_reason(code: str) -> str:
    return HUMAN_REASONS.get(code, code.replace("_", " "))
