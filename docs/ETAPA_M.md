# Etapa M — Estabilización del ejecutor automático

**Fecha:** 2026-11-03 · **Base:** `aa01ea9` / `checkpoint-etapa-l` · **Modo:** PAPER_ONLY · IA Shadow · sin órdenes reales.

## 1. Checkpoint y backup

| Ítem | Valor |
|------|--------|
| Pre-tag | `checkpoint-pre-etapa-m` |
| Backup pre | `backups/paper_pre_etapa_m_20261103_154043.sql` |
| Backup post | `backups/paper_post_etapa_m_20261103.sql` |
| Volúmenes | Intactos (`paper_data`, `ml_artifacts`) |
| Claves Binance | No introducidas |

## 2. Seguridad (M.1)

- `LAB_CONTROL_TOKEN` obligatorio vía `${LAB_CONTROL_TOKEN:?…}` en `compose.yaml` (api + trade-executor).
- Sin fallback a `paper`. Ausencia de env → HTTP 503; token incorrecto → 401.
- Mutaciones (`POST /api/lab/pause|resume|cycle`) con header `X-Lab-Token`.
- Token no se escribe en logs/audit. UI solo en `sessionStorage`.
- Verificado: sin token → 401; token `paper` → 401; token válido → 200.

## 3. Ciclo autónomo (M.2 / M.7)

Auditoría del pipeline: velas cerradas → SMA → señal → riesgo → orden lab → ledger lab.

**Ciclos orgánicos registrados** (`lab_cycles` id 1–5): todos HOLD (15 símbolos), 0 BUY/SELL naturales, 0 fills orgánicos. Motivo dominante: `no_sma_cross_on_closed_bar` (solo velas cerradas).

Evidencia: `docs/etapa_m_cycles_organic.json`, `docs/etapa_m_cycle_organic.json`, logs `LAB_CYCLE`.

**No se fabricaron cruces SMA** para aprobar la auditoría. Compras/ventas simuladas previas (demo Etapa L, `demo_verification=true`) siguen en el ledger lab para MTM/fees; no son señales orgánicas.

## 4. Valoración MTM (M.3)

`app/lab/valuation.py`: cash, costo, mark, MV, P/L realizado/no realizado, patrimonio, fees, retorno, drawdown; origen/timestamp del precio. Sin marks válidos → `valuation_status=INCOMPLETE` (sin inventar equity).

Estado observado: MTM **OK**, cash/equity lab ≈ 999.87, realized ≈ -0.13, fees ≈ 0.05, sin posiciones abiertas.

## 5. Salidas / breaker (M.4–M.5)

- Unit tests: stop gap (precio trigger ≠ fill), time-stop 48 barras, pause bloquea BUY, resume bloqueado si breaker crítico.
- Circuit breaker: eventos en `lab_breaker_events`; no auto-resume con condición crítica.
- Estado runtime: breaker **inactivo**.

## 6. Dashboard (M.6)

`/auto-trade` muestra ejecutor, estrategia, pausa/breaker, cash/patrimonio, P/L, ciclos, HOLD, trades, integridad de 3 ledgers, token UI.

Captura: `docs/etapa_m_dashboard_auto_trade.png`.

## 7. Pruebas (M.8)

```
113 passed, 1 skipped (compose.yaml no va en imagen API)
```

Nuevos: `backend/tests/test_etapa_m.py` (token, auth, compose, MTM, SL gap, time-stop, resume, pause, ledgers).

## 8. Contenedores (6)

| Servicio | Estado |
|----------|--------|
| db | Up (healthy) |
| api | Up |
| worker | Up |
| dashboard | Up (:8088) |
| shadow-scheduler | Up |
| trade-executor | Up |

## 9. Integridad de tres ledgers

| Ledger | Observado |
|--------|-----------|
| SMA paper (`account`) | cash **875**, 5 pos, 5 trades — **sin cambio** |
| research_sim (`virt_accounts`) | cash **1000** — **sin cambio** |
| lab_auto | cash **999.865…**, 2 trades lab (demo) |

Aislamiento verificado en status `integrity` y queries SQL.

## 10. Compras/ventas simuladas

| Orden | Side | Status | Nota |
|-------|------|--------|------|
| 1 | BUY BTCUSDT | FILLED | demo_verification (no cruce orgánico) |
| 2 | SELL BTCUSDT | FILLED | demo_verification_sell; fill ≠ mid puro (fee/slip) |

Salidas SL/TP/time validadas en tests unitarios (sin posición abierta orgánica en este momento).

## 11. Problemas pendientes

- Sin cruces SMA orgánicos en la ventana observada → no hay fills autónomos nuevos (esperado; documentado HOLD).
- Test `compose.yaml` se omite dentro de la imagen API (sí se valida en host).
- No declarar rentabilidad ni readiness de producción.

## 12. Rollback

```powershell
git checkout checkpoint-pre-etapa-m
# o: git reset --hard checkpoint-etapa-l
Get-Content backups\paper_pre_etapa_m_20261103_154043.sql | docker compose exec -T db psql -U paper -d paper
docker compose up -d --build
```

**No** borrar volúmenes. Restaurar `.env` con `LAB_CONTROL_TOKEN` fuerte (nunca `paper`).
