# Etapa N — Operación continua y señales orgánicas

**Fecha:** 2026-11-03 · **Base:** `0a7e979` / `checkpoint-etapa-m` · **Modo:** PAPER_ONLY · Shadow AI sin ejecución.

## 1. Commit y checkpoint

| Ítem | Valor |
|------|--------|
| Pre-tag | `checkpoint-pre-etapa-n` |
| Post-tag | `checkpoint-etapa-n` |
| Backup pre | `backups/paper_pre_etapa_n_20261103.sql` |
| Backup post | `backups/paper_post_etapa_n_20261103.sql` |

## 2. Backup verificado

Dump PostgreSQL generado sin tocar volúmenes. `.env` / token fuera de git.

## 3. Contenedores (6)

db (healthy), api, worker, dashboard, shadow-scheduler, trade-executor — **Up**.

## 4. Ciclos observados

≥15 ciclos lab. Ejemplos:

| Ciclo | BUY | SELL | HOLD | Filled | Rejected |
|-------|-----|------|------|--------|----------|
| 1–8 | 0 | 0 | 15 | 0 | 0 |
| 9 | 2 | 2 | 11 | 2 | 2 |
| 10–15 | 2 | 2 | 11 | 0* | 0 |

\* Re-detección de la misma vela → idempotencia (sin duplicar fills).

## 5. Señales orgánicas

Persistidas en `lab_signals` (cruces) y auditadas en `lab_signal_evals` (todas las decisiones):

- **BUY** BTCUSDT, ZECUSDT (`sma10_cross_above_sma50_closed`, closed-only).
- **SELL** USDCUSDT, RLUSDUSDT (`sma10_cross_below_sma50_closed`) — sin posición → rechazo.
- Evaluaciones 24h (muestra post-N): BUY 4 · SELL 4 · HOLD 22 · cruces 8.
- Cada eval registra: UTC, vela, SMA10/50, cruce, decisión, motivo, data_status, risk_status.

## 6. Compras / ventas virtuales lab

| Tipo | Detalle |
|------|---------|
| BUY orgánico FILLED | BTCUSDT budget 25 @ ~78047 (fee/slip) |
| BUY orgánico FILLED | ZECUSDT budget 25 @ ~1227.95 |
| SELL demo previa | BTCUSDT (Etapa L, `demo_verification`) |
| Posiciones abiertas | BTCUSDT, ZECUSDT (esperando SL/TP/time/SMA SELL) |

No se fabricaron cruces; no se cambiaron parámetros SMA para forzar trades.

## 7. Órdenes rechazadas

| Orden | Motivo |
|-------|--------|
| SELL USDCUSDT | `no_position` |
| SELL RLUSDUSDT | `no_position` |

Re-ciclos posteriores: 0 nuevas órdenes (UNIQUE por vela).

## 8. Estado del ledger

| Ledger | Cash / estado |
|--------|----------------|
| SMA paper | **875** (5 pos, 5 trades) — intacto |
| research_sim | **1000** — intacto |
| lab_auto | **≈949.87** cash · equity MTM ≈999.92 · fees ≈0.10 |

## 9. Pruebas

```
124 passed, 1 skipped
```

Nuevo: `backend/tests/test_etapa_n.py` (SMA BUY/SELL sintético aislado, prioridad salidas, stale, monitor dedup, idempotencia, sin endpoints reales).

## 10. Métricas disponibles

Observabilidad API/dashboard: ciclos/hora, evaluaciones, cruces, aceptadas/rechazadas, fees, slippage est., breaker, última vela, historial equity diario, P/L realizado/no realizado.

**No se declara rentabilidad robusta** — muestra corta, 2 buys orgánicos abiertos.

## 11. Alertas / anomalías

Monitor `lab_alerts` activo; 0 alertas al cierre de Etapa N. No auto-reanuda en crítico.

## 12. Captura dashboard

`docs/etapa_n_dashboard_auto_trade.png`

## 13. Pendientes

- Salidas SL/TP/time aún no disparadas en vivo (posiciones recientes; umbrales intactos).
- SELL SMA sobre stables sin posición → rechazo esperado; filtrar SELL sin inventario es mejora opcional.
- Observación continua recomendada hasta más horizontes.

## 14. Rollback

```powershell
git checkout checkpoint-pre-etapa-n
# o: git reset --hard checkpoint-etapa-m
Get-Content backups\paper_pre_etapa_n_20261103.sql | docker compose exec -T db psql -U paper -d paper
docker compose up -d --build
```

Conservar `LAB_CONTROL_TOKEN` fuerte. No borrar volúmenes.
