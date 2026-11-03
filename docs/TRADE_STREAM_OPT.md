# Trade stream — optimización (latencia + suscripciones)

## Checkpoint

| | |
|--|--|
| Pre | `checkpoint-pre-trade-opt` (`5fe21db`) |
| Tag | `checkpoint-trade-opt` |
| Backup | `backups/paper_pre_trade_opt_20261103.sql` |

## Auditoría confirmada

- `@trade` + `@kline_<interval>` activos
- Agregación OHLCV + dedupe trade id
- Coalesce 16 ms · rAF · `series.update`
- Reconexión con debounce de resubscribe
- PAPER_ONLY · sin órdenes reales

## Latencia (separada)

| Métrica | Reloj | Ejemplo medido |
|---------|-------|----------------|
| Binance event → hub_recv | wall (skew-aware) | p50/p95/p99 ≈ **96/99/99 ms** (n=154) |
| hub_recv → emit | monotonic local | p50 ≈ **16.4 ms** (coalesce) |
| browser recv → paint | performance.now | p50/p95/p99 ≈ **1/6/198 ms** |
| Edad último trade | wall | ~110 ms |
| Skew estimado | wall Δ server_send | ~±2 ms |

Negativos descartados. No se mezclan monotónicos entre hosts.

## Suscripciones compartidas

- Registro `SYMBOL:interval` → N colas
- 2 clientes BTCUSDT 1m → **1** `upstream_connections`, streams `btcusdt@trade`+`kline_1m`
- Liberación al llegar a 0 consumidores
- Debounce 80 ms en cambios de stream set

## Pruebas

`27 passed` (hub subscriptions, aggregator, normalize, guards, overlay)

## Recursos / Docker

market-stream ~0.5% CPU / ~38 MiB · 7 contenedores Up

## Ledgers

`sma_trades=9 lab_trades=5 sma_pos=9 lab_pos=3`

## Captura

`docs/etapa_trade_opt_btcusdt_live.png`

## Pendiente

- StrictMode/doble pestaña puede dejar 2 clientes WS (esperado; un solo upstream)
- paint p99 puntual alto en primer frame tras carga
