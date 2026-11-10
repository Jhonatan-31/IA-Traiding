# Etapa W — Historial profesional de mercado

**Fecha:** 2026-11-10  
**Base:** `checkpoint-etapa-v` / commit `4549de7`  
**Pre-W:** `checkpoint-etapa-w-pre-20261110_115036` · `backups/paper_pre_etapa_w_*.dump`

## Seguridad

- A STOPPED · B STOPPED · PAPER_ONLY · PAPER_AI off
- Sin activación de estrategias nuevas
- Historial aislado en `data/market_history` (bind → `/artifacts/history`)
- Ledgers operativos intactos

## Fuente

- https://data.binance.vision/ (Spot monthly klines 1m)
- Docs: https://github.com/binance/binance-public-data
- Checksums `.CHECKSUM` (SHA-256) verificados cuando existen
- Timestamps normalizados ms/µs/s

## Tubería

1. Descarga ZIP idempotente + reanudable  
2. Validación OHLC / orden / duplicados / huecos (**sin fabricar velas**)  
3. Parquet particionado `symbol=/interval=/year=/month=`  
4. Agregación reproducible: 5m, 15m, 1h, 4h, 1d (solo buckets cerrados)  
5. Metadatos en PostgreSQL (`research_history_*`) — no OHLC operativo masivo  

## Ventana de investigación

- **Fija:** 2024-11 → 2025-10 (12 meses calendario)  
- No se eligió por rendimiento aparente  
- Holdout final ~10% del backtest W **no** se usa para ajustar parámetros  

## Smoke (validación de tubería)

- BTCUSDT 2025-10  
- Checksum match: sí  
- ~44 640 velas 1m · TF superiores generados  

## Criterio

Más historial **no** declara rentabilidad. Sirve para rechazar hipótesis débiles con evidencia suficiente.
