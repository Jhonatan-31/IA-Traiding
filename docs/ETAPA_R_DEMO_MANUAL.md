# Etapa R — Trading Automático DEMO (control manual persistente)

## Checkpoint / backup

- Git HEAD base: `112ecc7` · tag pre: `checkpoint-etapa-r-pre-*`
- Backup: `backups/paper_pre_etapa_r_*.dump`
- Política congelada: `docs/DEMO_POLICY_v1.md` (`demo_policy_v1_20261103`, entrada **4/5**)

## Qué hay

| Pieza | Detalle |
|-------|---------|
| Ledger | `demo_manual_control` · 1000 USDT · **no se resetea** al reiniciar |
| Runner | `demo-runner` (compose) · ciclo 60s · independiente del navegador |
| Control | `POST /api/demo/start\|stop` + `X-Lab-Token` (LAB_CONTROL_TOKEN) |
| Estado | `demo_state.status` STOPPED/RUNNING en PostgreSQL |
| UI | `/demo` — Trading Automático DEMO |
| Marcadores | `GET /api/demo/markers?symbol=` mezclados en Gráficas (ledger tag DEMO) |

## Comportamiento verificado

1. STOPPED → runner evalúa pero `allow_entries=false` → HOLD `bot_stopped_entries_blocked`
2. START → RUNNING en DB/API; doble START → `already_running`
3. RUNNING → señales con `flags_N_of_5_insufficient` (sin forzar BUY)
4. STOP → STOPPED; doble STOP → `already_stopped`; nuevas entradas bloqueadas
5. Reinicio API → estado **STOPPED** y cash **1000** persistidos
6. Auth sin token → **401**
7. Tests: `tests/test_demo_control.py` (+ counters) **6 passed**
8. Ledgers ajenos intactos (sma 775, lab, research 1000, express 100)

## Endpoints

- GET `/api/demo/status|decisions|orders|fills|positions|performance|markers`
- POST `/api/demo/start|stop` (token)

## Limitaciones

- Sin fills aún: mercado no cumplió 4/5 en la ventana de prueba (correcto; no se forzaron).
- SL/TP protectores activos con posiciones; sin inventario no hay ventas.
- Score ≠ probabilidad calibrada (`probability_validated=false`).
- No es validación estadística de rentabilidad.

## Rollback

1. `docker compose stop demo-runner`
2. Opcional: dropear solo tablas `demo_*` (no tocar paper_data volume completo)
3. Restaurar dump: `pg_restore` desde `backups/paper_pre_etapa_r_*.dump` si hace falta
4. Revertir código al tag `checkpoint-etapa-r-pre-*`
5. **Nunca** `docker compose down -v`

## Seguridad

PAPER_ONLY · PAPER_AI off · sin órdenes reales · sin alterar SMA/Lab/Shadow/Express balances por el motor DEMO.
