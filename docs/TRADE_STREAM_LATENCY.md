# Trade stream — latencia ultra-baja (visualización)

## Diagnóstico previo (medido)

| Hallazgo | Valor |
|----------|--------|
| Canal anterior | Solo `btcusdt@kline_1m` |
| Intervalo entre klines | p50 ≈ **1997 ms** (no 60 s) |
| Trades en 12 s | **641** (~53/s) |
| recv−E trade p50/p95/p99 | **106 / 194 / 237 ms** (incluye skew de reloj) |
| Polling artificial UI | No (WS); React sí hacía `setState` por kline |
| Render LWC | Ya usaba `series.update` en ticks |

Conclusión: el cuello de botella no era un timer de 60 s, sino la **cadencia del stream kline (~2 s)** frente a decenas de trades/segundo.

## Implementación

- Upstream: `<symbol>@trade` + `<symbol>@kline_<interval>`
- Agregación OHLC+volumen por trade; kline cierra/reconciliación oficial
- Fan-out coalesce **16 ms** (≈1 frame), sin delay de 1 s
- Frontend: `requestAnimationFrame` + `applyLive` imperativo (sin remount/`setData` por tick)
- Dedupe por trade id; rechaza atrasados / vela cerrada

## Validación UI (BTCUSDT 1m)

- `CONNECTED` + badge **LIVE** + `src trade`
- ticks creciendo (p.ej. 21 → 92) dentro del mismo minuto
- streams: `btcusdt@kline_1m,btcusdt@trade`
- Captura: `docs/etapa_trade_stream_btcusdt_1m.png`

## Latencia observada post-cambio

| Tramo | Muestra |
|-------|---------|
| Binance→hub (EWMA / p50) | ~100–105 ms |
| hub→UI | ~3–200 ms (varía con skew Docker/host) |
| Coalesce hub | 16 ms |

No se promete latencia cero.

## Checkpoint

- Pre: `checkpoint-pre-trade-stream` (`0166cf9`)
- Tag: `checkpoint-trade-stream`

## Seguridad

PAPER_ONLY. Trades no ejecutan SMA/Shadow/Lab. Ledgers intactos.
