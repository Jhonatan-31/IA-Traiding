# Etapa AA — Informe técnico

## Identidad congelada

| Campo | Valor |
|---|---|
| Target | Z-TSMOM-D28H5 |
| Config hash | `5326edb8a539cfe5` (match) |
| Commit base Z | `614bb9d78710a4c27bd50505577f05b582a00d7a` |
| Ejecutable | `make_tsmom(28)` diario |
| `min_hold=5` | Solo meta; **no** en código |
| Costos | fee 10 bps + slip 5 bps + spread 1 bps |
| Capital | 1.000 USDT |

## Datos

- Fuente: https://data.binance.vision/ Spot klines 1d
- Símbolos: BTCUSDT, ETHUSDT, SOLUSDT
- Meses AA: 2025-11 … 2026-10 (36 particiones)
- Warm-up: 1d 2024-11 … 2025-10 ya presente
- Sin fabricar velas; checksums vía pipeline Vision

## Motor

- Señales sobre closes cerrados; índice `i` no lee futuro
- Suite sintética: 5/5 OK (up, down→cash, flat, BH-EQ, jump)
- Look-ahead contract: fixtures + nota de causalidad

## Bugs / correcciones durante AA

1. `make_tsmom(28)()` incorrecto en synthetic → `make_tsmom(28)`
2. Independencia: usar etiqueta **pre-ingesta** (post-download no implica uso previo)
3. `iter_months` / imports: corregidos en prerregistro de código

Ninguna corrección alteró parámetros de D28H5. Repetición one-pass con `--skip-ingest` tras fallo sintético: **correctiva de motor**, misma ventana; marcada consumida una vez.

## Artefactos

- `/artifacts/history/etapa_aa_results.json`
- Archivo experiment id `AA-20261113T150418Z`

## Microestructura (AA8)

No mezclada con evaluación primaria. Sin BBO/aggTrades en Parquet.
