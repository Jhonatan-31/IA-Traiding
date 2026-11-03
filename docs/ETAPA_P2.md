# Etapa P — Fase 2: Terminal profesional

## Checkpoint

| Ítem | Valor |
|------|--------|
| Pre | `checkpoint-pre-etapa-p2` (`fe6ec95`) |
| Backup | `backups/paper_pre_etapa_p2_20261103.sql` |
| Tag fase 2 | `checkpoint-etapa-p2` |

## Entregado

- Marcadores SMA / Lab / Shadow con toggles; predicciones ≠ ejecuciones
- Líneas ENTRY / SL / TP / MARK desde DB (Lab tiene SL/TP; SMA solo entry+mark)
- Tarjetas de posiciones por ledger y símbolo
- Historial incremental (`end_time`) + dedupe + preservación de viewport
- Botón «Volver al tiempo real»
- Indicadores SMA/EMA/BB/RSI/MACD/ATR + paneles sync
- Tooltip OHLCV + estados WS
- Tests: `test_chart_overlay.py`, `test_ws_client_guards.py` (+ market_stream) → 15 passed

## Evidencia UI

- `docs/etapa_p2_btcusdt_1m.png` — PRED BUY, líneas ENTRY Lab/SMA
- `docs/etapa_p2_ethusdt_5m.png` — CONNECTED ETH 5m + markers
- `docs/etapa_p2_solusdt_1h.png` — LAB ENTRY/SL/TP + SMA ENTRY

## Integridad ledgers (sin cambio por gráficas)

`sma_trades=9 lab_trades=5 sma_pos=9 lab_pos=3` (mismo conteo pre/post)

## Pendiente menor

- Auto-carga histórica puede acumular ~900 barras al montar (from&lt;10); valorar debounce más estricto
- LWC v4: un marker por timestamp (se colapsan duplicados)
- SMA sin SL/TP en schema (esperado)

## Rollback

```powershell
git checkout checkpoint-pre-etapa-p2
docker compose up -d --build
```
