# Etapa O — Ventas automáticas, posiciones y riesgo

**Fecha:** 2026-11-03 · **Base:** `a691814` / `checkpoint-etapa-n` · PAPER_ONLY · Shadow AI · PAPER_AI off.

## 1. Commit y checkpoint

| Ítem | Valor |
|------|--------|
| Pre | `checkpoint-pre-etapa-o` |
| Post | `checkpoint-etapa-o` |
| Backup pre | `backups/paper_pre_etapa_o_20261103.sql` |
| Backup post | `backups/paper_post_etapa_o_20261103.sql` |

## 2. Backup

PostgreSQL dump verificado; volúmenes intactos; sin claves Binance reales.

## 3. Estado inicial BTC / ZEC (y SOL orgánica posterior)

Al inicio de O (operación continua ya había añadido SOL):

| Símbolo | Qty | Entrada | Coste | SL (−2%) | TP (+4%) | Max bars | bars rest. (obs.) |
|---------|-----|---------|-------|----------|----------|----------|-------------------|
| BTCUSDT | ~0.00032032 | ~78047.42 | 25 | ~76486.47 | ~81169.32 | 48 | ~46 |
| ZECUSDT | ~0.02035918 | ~1227.95 | 25 | ~1203.39 | ~1277.06 | 48 | ~46 |
| SOLUSDT | ~0.266223 | ~93.91 | 25 | ~92.03 | ~97.66 | 48 | ~47 |

Lab cash ≈ **924.87** (referencia N era ~949.87 antes del BUY SOL).  
Respaldo ledger: filas en `lab_positions` + trades BUY en `lab_trades`.  
SMA paper / research_sim no mutados por lab.

Evidencia: `docs/etapa_o_positions_initial.json`.

## 4. Cambios implementados

- `positions_audit.py`: mark observado vs ejecución estimada (−slip), SL/TP, barras restantes.
- `can_protective_sell` + política explícita: breaker bloquea compras; ventas protectoras permitidas; pausa operador bloquea todo; sin liquidar sin mark fresco.
- Señales SMA SELL: **no encolan** orden si no hay inventario (`sell_skipped_no_position`).
- Motivo de salida propagado (`strategy_exit` / SL / TP / time).
- Dashboard: posiciones con SL/TP/tiempo, historial de ventas, patrimonio.
- Tests aislados Etapa O (sin falsificar producción).

## 5. Pruebas

```
139 passed, 1 skipped
```

Incluye: SL, TP, time stop, SMA SELL, prioridad, stale, fees/slip, no inventario, idempotencia post-venta, breaker vs protective sell, PAPER_ONLY.

## 6. Ventas naturales observadas

**Cero ventas orgánicas de cierre** en la ventana O.

Motivos: precios lejos de SL/TP; time stop no vencido (~46–47 barras restantes); sin SMA SELL sobre BTC/ZEC/SOL abiertas.  
Parámetros **no** se modificaron para forzar cierres.

Única SELL histórica en ledger: demo Etapa L (`demo_verification_sell`) — no cuenta como orgánica O.

## 7. Cierres en tests aislados

Verificados sintéticamente: stop-loss (trigger ≠ fill), take-profit, max_hold_bars, strategy_exit, prioridad SL>TP>time>SMA, fee/slip en `apply_sell`, segundo sell → `no_position`.

## 8. Integridad ledger

| Ledger | Estado |
|--------|--------|
| SMA `account` | cash 825 (worker SMA propio; no tocado por lab) |
| `research_sim` | 1000 |
| `lab_auto` | cash ≈924.87 · 3 posiciones · equity MTM ≈999.6 |

## 9. Circuit breaker

Inactivo. Política: bloquea BUY; protective SELL permitido con mark fresco; pausa auditable vía API token.

## 10. Docker

6 servicios Up (db healthy, api, worker, dashboard, shadow-scheduler, trade-executor).

## 11. Captura

`docs/etapa_o_dashboard_auto_trade.png`

## 12. Pendientes

- Esperar cruces SMA SELL o umbrales SL/TP/time en observación continua.
- No declarar rentabilidad.
- Opcional: filtrar universe de SELL-only symbols ya cubierto al no encolar sin posición.

## 13. Rollback

```powershell
git checkout checkpoint-pre-etapa-o
Get-Content backups\paper_pre_etapa_o_20261103.sql | docker compose exec -T db psql -U paper -d paper
docker compose up -d --build
```
