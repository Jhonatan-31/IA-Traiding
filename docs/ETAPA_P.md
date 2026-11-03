# Etapa P — Gráficas en tiempo real (fase 1: BTCUSDT 1m)

## Auditoría previa

| Ítem | Hallazgo |
|------|----------|
| Lightweight Charts | `^4.2.2` (API v4: `addCandlestickSeries`) |
| ChartsPage / CandleChart | REST polling; `setData` completo por reload |
| `/api/candles` | OHLCV + indicadores server-side + markers SMA `trades` |
| Nginx | Solo `/api/` → api |
| Docker | 6 servicios; se añade `market-stream` (7º) |
| Trading | PAPER_ONLY; sin claves privadas |

## Arquitectura

```
Browser ──WS /ws/market──► market-stream ──WS──► Binance public stream
Browser ──REST /api/candles──► api (historial + indicadores)
```

`market-stream` concentra una conexión upstream por conjunto de streams y hace fan-out a navegadores. No toca DB ni ledgers.

## Fase 1 entregada

- Servicio `market-stream` con reconexión/backoff, ping, renovación 20h, stale detect.
- `WS /ws/market`, `GET /api/market/status`, `GET /health`
- Charts: default **BTCUSDT 1m**, actualización incremental `series.update()`, follow toggle, estados CONNECTED/RECONNECTING/STALE/DISCONNECTED
- Historial REST + live WS; no `setData` en cada tick
- Tests `test_market_stream.py` (6 passed)
- Commit `c033793` · tag `checkpoint-etapa-p` · pre `checkpoint-pre-etapa-p` (`518e155`)
- Backup `backups/paper_post_etapa_p_20261103.sql`
- Evidencia UI: `docs/etapa_p_charts_btcusdt_1m_live.png` (CONNECTED, vela abierta live, precio WS)

## Verificación BTCUSDT 1m (2026-11-03)

| Prueba | Resultado |
|--------|-----------|
| Smoke WS → Binance kline | LIVE_OK |
| UI `/charts` estado | CONNECTED |
| Precio live | ~77778 (evt WS) |
| Incremental | badge «Vela abierta (live)» |
| pytest market_stream | 6 passed |
| Ledgers / estrategias | sin cambios de parámetros |

## Pendiente (siguientes iteraciones)

- Markers Lab / Shadow separados con toggles
- Líneas SL/TP de posiciones lab
- Carga histórica al scroll (más velas)
- ATR panel / más símbolos por defecto en barra
- Pruebas e2e de WS con mock

## Rollback

```powershell
git checkout checkpoint-pre-etapa-p
docker compose up -d --build
# quitar market-stream del compose si se restaura versión previa
```
