# Etapa X — Diagnóstico por régimen y estructura

**Fecha:** 2026-11-10  
**Base:** `0247960` / `checkpoint-etapa-w`  
**Pre-X:** `checkpoint-etapa-x-pre-20261110_144121`

## Seguridad

A STOPPED · B STOPPED · PAPER_ONLY · PAPER_AI off · sin activaciones.

## Base histórica (confirmada)

| Chequeo | Resultado |
|---|---|
| Fuente | Parquet Binance Vision (no REST limit 1000) |
| Span 1m | 2024-11-01 → 2025-10-31 · 525 600 velas/símbolo · 100% verificado |
| Simulación | **1h** agregada · **8760** barras/símbolo |
| `not_rest_limit_1000` | **True** |

### Unidades de rendimiento

- `net_pnl` / `expectancy` / `net_vs_initial`: **USDT** sobre capital simulado **1000 USDT** (no %).
- `buy_hold_proxy_return` / MFE/MAE / drawdown: **fracciones** (0.01 = 1%).
- Costos fee≈10 bps + slip≈5 bps ya embebidos en fills.

## Cómo se identifican los regímenes

Clasificador **causal** (solo historia hasta la barra):

- **Tendencia:** EMA20 vs EMA50 + slope 20 barras → uptrend / downtrend / sideways  
- **Volatilidad:** ATR% 14 → high (≥1.2%) / normal / low (≤0.4%)  
- **Volumen:** vol / SMA20 → high (≥1.5) / normal / low (≤0.7)  

Sin look-ahead. MFE/MAE son métricas **diagnósticas post-entrada**, no entran en la decisión de compra.

## Qué regímenes existieron (BTC 1h, barras)

| Régimen | Barras |
|---|---:|
| uptrend\|normal_volatility | 2202 |
| sideways\|normal_volatility | 2089 |
| downtrend\|normal_volatility | 1769 |
| sideways\|low_volatility | 1177 |
| uptrend\|low_volatility | 564 |
| downtrend\|low_volatility | 276 |
| downtrend\|high_volatility | 272 |
| sideways\|high_volatility | 207 |
| uptrend\|high_volatility | 144 |

## Resultados globales (IS+OOS; holdout W excluido)

| Estrategia | Ops | Neto USDT | Expectativa | WR | Fees |
|---|---:|---:|---:|---:|---:|
| A_BASELINE | 436 | −19,15 | −0,044 | 37% | 21,79 |
| V_TREND | 0 | 0 | — | — | 0 |
| V_BREAK | 250 | −18,59 | −0,074 | 36% | 12,49 |
| V_MEAN | 221 | −15,62 | −0,071 | 44% | 11,06 |
| Efectivo | — | 0 | — | — | — |
| Buy&hold proxy | — | — | +62% (fracción) | — | — |

## Dónde pierden (N≥30)

- **A:** sideways\|normal (−0,124 USDT/op, 93 ops); uptrend\|normal (−0,050, 126 ops)  
- **V-BREAK:** sideways\|high (−0,285, 36); sideways\|normal (−0,169, 69)  
- **V-MEAN:** sideways\|high (−0,096, 54); sideways\|normal (−0,054, 152)  
- **V-TREND:** sin operaciones → hipótesis de tendencia no testeable en 1h con reglas actuales  

## Segmentos con expectancy >0 (exploratorio)

| Estrategia | Régimen | N | Expectativa |
|---|---|---:|---:|
| A | sideways\|high_volatility | 75 | +0,0004 |
| V-BREAK | uptrend\|normal_volatility | 86 | +0,052 |

**Ninguno es robusto:** bootstrap por bloques no deja CI95 enteramente >0.  
`robust_positive_segments = []`.

No se promocionan: riesgo de selección retrospectiva entre muchos segmentos.

## Calidad de señales (entradas vs salidas)

| Estrategia | avg MFE | avg MAE | ¿Entrada? | ¿Salida? |
|---|---:|---:|---|---|
| A | 1,64% | 1,44% | no dominante | **sí** (deja MFE sobre la mesa) |
| V-BREAK | 2,19% | 1,94% | no dominante | **sí** |
| V-MEAN | 1,23% | 1,24% | **sí** (MAE≈MFE) | **sí** |

Lectura: A/V-BREAK a menudo **capturan mal el movimiento favorable** (problema de salida/timing). V-MEAN mezcla malas entradas y salidas. Costos (fees) son material frente a expectancy ~−0,04 a −0,07 USDT/op.

## Hipótesis predefinidas

| ID | Estado | Nota |
|---|---|---|
| H1 A peor en sideways\|low_vol | insufficient_n | Solo 5 ops |
| H2 V-BREAK + en uptrend\|high_vol | **rejected** | expectancy −0,030 |
| H3 V-TREND gana en uptrend | insufficient_n | 0 ops |
| H4 V-MEAN edge sideways\|low_vol | insufficient_n | 15 ops |

## Holdout W

**Consumido.** No se reutiliza para elegir estrategias.  
Validación independiente = datos **posteriores a 2025-10-31** (aún no ingeridos en esta etapa).

## Conclusiones

1. **Resultados globales siguen siendo negativos** para A, V-BREAK y V-MEAN.  
2. V-TREND no genera trades en 1h → descartar como está o reformular reglas (investigación, no activación).  
3. Segmentos “positivos” exploratorios **no resisten** bootstrap ni corrección por múltiples pruebas.  
4. **No hay evidencia robusta** para activar ni para prueba prospectiva automática.  
5. Hipótesis a seguir investigando (sin crownear holdout):  
   - filtrar V-BREAK solo uptrend\|normal (requiere validación out-of-time nueva)  
   - endurecer salidas (trail / captura de MFE) en A  
6. Hipótesis a descartar por ahora: edge de V-MEAN en lateral; edge V-BREAK en alta vol alcista; operar A sin filtro de régimen.

## Entregables

- Código: `diagnose_x.py`, `regimes_x.py`, `center_x.py`, panel UI  
- Tests: `tests/test_etapa_x.py`  
- Dashboard: `/investigacion` → «¿Cuándo tiene sentido operar?»  
- Rollback: `docs/etapa_x_rollback.md`
