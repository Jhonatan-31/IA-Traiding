# Pausa segura — Estrategia A (Bot Demo)

| Campo | Valor |
|---|---|
| Mecanismo | `POST /api/demo/stop` + `X-Lab-Token` |
| Hora UTC pausa | **2026-11-10T15:25:49.237318Z** |
| Antes | RUNNING · cash ≈966,37 · equity ≈966,37 · 1 pos BTC · 0 BUY pendientes |
| Después | **STOPPED** · mismo cash/posiciones · compras bloqueadas |
| BUY canceladas | 0 (no había pendientes NEW/VALIDATED) |
| Protecciones | `protective_exits_remain: true` en evento STOP |
| Runner | `demo-runner` Up (no finalizado) |
| B | STOPPED · cash 1000 (intacta) |
| PAPER_ONLY | sí · sin órdenes reales Binance |

## Evidencia post-ciclo (STOPPED)

Log: `allow_entries: false`, `bot_status: STOPPED`  
Decisiones: BTC `hold_position` (posición bajo vigilancia) · ETH/SOL `bot_stopped_entries_blocked`  
`last_eval_at` y `heartbeat_at` siguen actualizándose · `connection_ok=true`

## Otras carteras

| Ledger | Estado |
|---|---|
| active_exp_v1 (B) | STOPPED · 1000 |
| lab_auto | cash ≈997,89 (sin cambio de estado por esta pausa) |
| research_sim | 1000 |
| express_test_20261103 | 100 |

## Pruebas

`tests/test_demo_stop_protections.py` → **4 passed** (BUY bloqueado, STOP persiste protecciones, gates en motor).
