# AA0 — Manifiesto inmutable de evaluación (pre-resultados nuevos)

**Creado antes de inspeccionar retornos del período post-2025-10.**  
Commit base: `614bb9d` · Tag: `checkpoint-etapa-z` · Pre-tag AA: `checkpoint-etapa-aa-pre-20261113_095420`

## Identidad de la estrategia evaluada

| Campo | Valor verificado |
|-------|------------------|
| ID | `Z-TSMOM-D28H5` |
| config_hash Etapa Z | `5326edb8a539cfe5` |
| Código de pesos | `WEIGHT_BUILDERS["Z-TSMOM-D28H5"]` → `make_tsmom(28)` en `engine.py` |
| Universo | BTCUSDT, ETHUSDT, SOLUSDT |
| Temporalidad | 1d cerrada |
| Lookback | 28 días |
| Señal | Si retorno close[t]/close[t−28]−1 > 0 → activo elegible |
| Pesos | Equiponderado entre elegibles; si ninguno → 100% cash |
| Rebalanceo | **Diario al close** (tras señal de vela cerrada) |
| Fee | 0.001 (10 bps) |
| Slip | 0.0005 (5 bps) |
| Spread proxy | 1.0 bp (half en one-way via `/20000`) |
| Capital | 1000 USDT |
| Long-only Spot | sí · sin apalancamiento |

## Aclaración crítica de fidelidad (no cambia la evaluación)

El nombre/título dice «hold 5d» y `params.min_hold=5` aparece en la ficha, **pero el código congelado no aplica `min_hold`**: reevalúa cada día.  
**La evaluación AA usa el comportamiento ejecutable (`make_tsmom(28)`), no una reconstrucción “H5” distinta.**  
Esto se registra para no inventar una especificación más estricta que la que produjo el +341 USDT de Z.

## Contabilidad Z (reconciliación conceptual)

Del artefacto Z OOS (`period_bars=73`, índices 255→328):

| Concepto | Valor Z |
|----------|---------|
| Neto D28H5 | +340.5377 USDT |
| Equity final | 1340.5377 |
| turnover_events | 136 |
| fees_and_frictions | 23.05 |
| avg_exposure | 0.947 |

**136 rebalanceos ≠ 136 operaciones round-trip.** Cada `turnover_events` cuenta un ajuste de notional (compra o venta parcial) cuando \|Δ\| ≥ 1 USDT.  
Antes de AA se re-ejecutará la misma ventana Z para comprobar reproducción del +340.54 (±tolerancia de float).

## Benchmark primario (prerregistrado)

**Z-BH-EQ**: pesos 1/3 diarios al close, mismos costos y motor.  
Secundarios: Z-BH-BTC, efectivo (neto 0).

## Modelo de ejecución (congelado)

Decisión tras close[i]; rebalance al close[i] con fee+slip+spread proxy; sin BBO histórico.
