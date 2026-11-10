# Etapa W — Informe final

**Fecha:** 2026-11-10  
**Base:** `4549de7` / `checkpoint-etapa-v`  
**Pre:** `checkpoint-etapa-w-pre-20261110_115036`

## Seguridad

| Chequeo | Estado |
|---|---|
| A | STOPPED · cash 990,81 |
| B | STOPPED · cash 1000 |
| PAPER_ONLY | sí |
| PAPER_AI | off |
| Estrategias nuevas | **ninguna activada** |

## Fuente y cobertura

- Fuente: [data.binance.vision](https://data.binance.vision/) Spot monthly 1m  
- Docs: [binance-public-data](https://github.com/binance/binance-public-data)  
- Ventana fija: **2024-11-01 → 2025-10-31** (12 meses)  
- Símbolos: BTCUSDT, ETHUSDT, SOLUSDT  
- Ingesta: **36/36** meses OK · checksums SHA-256 coincidentes  
- Velas 1m/símbolo: **525 600** · cobertura span **100%** · verificadas  
- TF generados: 5m, 15m, 1h, 4h, 1d (solo buckets cerrados)  
- Almacenamiento historial ≈ **136 MB** (Parquet+ZIP) en `data/market_history`  
- Metadatos PG: 216 archivos registrados (sin volcar OHLC operativo)

## Calidad

- Timestamps normalizados (ms/µs)  
- OHLC / orden / dedupe OK  
- Huecos registrados; **no se fabrican velas**  
- Disponible ≠ verificado (UI distingue ambos)

## Backtest largo (W)

- Motor: políticas congeladas A / V-TREND / V-BREAK / V-MEAN  
- Barras de simulación: **1h** agregadas desde 1m (8760/símbolo)  
- Walk-forward: 70% IS / 20% OOS / **10% holdout no usado para decidir**  
- Costos: fee 10 bps + slip 5 bps  

### OOS (equivalente temporal)

| Estrategia | Neto | Ops | WR | PF | Fees | Slip | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| A_BASELINE | −0,88 | 190 | 39% | 0,98 | 9,50 | 4,75 | 0,82% |
| V_TREND | 0 | 0 | — | — | 0 | 0 | 0 |
| V_BREAK | −1,79 | 109 | 39% | 0,94 | 5,45 | 2,73 | 0,70% |
| V_MEAN | −4,40 | 42 | 38% | 0,57 | 2,12 | 1,06 | 0,46% |
| Buy&hold proxy | −7,7% | — | — | — | — | — | — |
| Efectivo | 0 | — | — | — | — | — | — |

### Holdout (informativo)

Todos los candidatos con operaciones: **neto ≤ 0**. V-TREND sin fills.

## Conclusión

**Ninguna estrategia es apta para prueba prospectiva** con los filtros de investigación.

Más historial permitió rechazar con mayor evidencia (V-BREAK/V-MEAN pierden OOS; V-TREND no opera; A sigue marginalmente negativa). No se declara rentabilidad.

## Pendientes

- Ampliar a 24 meses si disco lo permite  
- Backtest nativo 1m/15m con motor vectorizado (CPU)  
- MFE/MAE forense A con klines históricos  
- Deflated Sharpe con N efectivo mayor  

## Rollback

Ver `docs/etapa_w_rollback.md`.
