# Etapa T — Políticas A / B / C (versionadas)

Todas son PAPER_ONLY. Ninguna coloca órdenes reales en Binance.

## Estrategia A — Baseline conservadora

| Campo | Valor |
|---|---|
| ID cartera | `demo_manual_control` (existente, **no reiniciar**) |
| Versión | `demo_policy_v1_20261103` |
| Doc | `docs/DEMO_POLICY_v1.md` |
| Ejecución | Autorizada (Bot Demo actual) |
| Entrada | ≥4/5 flags + score≥0.80 |
| Salida | SL −1% · TP +2% · ruptura EMA/RSI |
| Estado Etapa T | Referencia inmutable |

## Estrategia B — Trading Activo

| Campo | Valor |
|---|---|
| ID cartera | `active_exp_v1` (**nueva**, aislada, 1000 USDT) |
| Versión | `active_policy_b_v1_20261104` |
| Doc | este archivo + `backend/app/active/policy_b.py` |
| Ejecución | PAPER tras validación técnica (integridad/backtest), **no** claim de alpha |
| Mercados | BTCUSDT, ETHUSDT, SOLUSDT |
| Velas | 1m y 5m **cerradas** |

### Entrada (estructura explícita — no conteo 4/5)

1. **Tendencia 5m:** EMA9_5m > EMA21_5m *(obligatoria)*  
2. **Impulso 1m:** EMA9_1m > EMA21_1m **o** close > close[−5]  
3. **RSI 14:** 42 ≤ RSI ≤ 68  
4. **Liquidez mínima:** volumen_1m ≥ 0.60 × SMA20(volumen) (piso, no spike)  
5. **Costos cubiertos:** ATR14%/precio ≥ 1.5 × (fee + slip) *(diferenciador vs Demo)*  
6. **Volatilidad no extrema:** ATR14%/precio ≤ 0.025  
7. Controles: cooldown 15 min/símbolo, máx 3 posiciones, 25 USDT/trade, exposición ≤75, máx 6 entradas/hora  

`fresh_impulse` se registra en flags (auditoría) sin bloquear la entrada.

### Salida

- Stop-loss −1%  
- Take-profit +2%  
- Cruce bajista EMA9/EMA21 en 1m **o** RSI < 40 con tendencia 1m bajista  

### Costos

Fee 10 bps · slip 5 bps (igual que Demo para comparación).

## Estrategia C — IA asistida (solo investigación)

| Campo | Valor |
|---|---|
| ID | observación sobre Shadow / `research_sim` |
| Versión | `active_policy_c_observe_v1_20261104` |
| Ejecución | **PROHIBIDA** hasta: modelo entrenado + versión + calibración + OOS + muestra suficiente + evidencia prospectiva |
| Estado actual | **IA NO VALIDADA** (`calibrated_probability` ausente) |

Combina lectura de predicciones Shadow con reglas técnicas solo para **registro** de señales hipotéticas. Sin fills. No PAPER_AI.
