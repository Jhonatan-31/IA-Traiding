# Etapa T.1 — Comparación operativa y diagnóstico de oportunidades

**Base:** commit `5bb231a` (Etapa T)  
**Checkpoint pre:** `checkpoint-etapa-t1-pre-20261110_100827`  
**Backup:** `backups/paper_pre_etapa_t1_20261110_100827.dump`  
**Modo:** PAPER_ONLY · sin PAPER_AI · sin cambio de reglas de entrada/salida

## 1. Estado real A / B / C (auditoría 2026-11-10 ~15:08 UTC)

| ID | Nombre | Ledger | Estado | Cash | Equity | Buys | Sells | Pos | rPnL |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| A | Conservadora | `demo_manual_control` | **RUNNING** | ≈942.67 | ≈992.15 | 52 | 50 | 2 | ≈−6.56 |
| B | Trading Activo | `active_exp_v1` | **STOPPED** | 1000.00 | 1000.00 | 0 | 0 | 0 | 0 |
| C | IA Experimental | observation | **IA NO VALIDADA** | — | — | 0 | 0 | 0 | — |

- A y B: start/stop independientes (`/api/demo` vs `/api/active`).
- B **no** se activó en T.1 (requiere autorización explícita del usuario + `X-Lab-Token`).
- C: `execution_authorized=false`, sin calibración (`calibrated_probability` ausente).
- Última decisión A: HOLD `flags_3_of_5_insufficient` (SOL).
- Última decisión B: HOLD `bot_stopped_entries_blocked` (esperado mientras STOPPED).

## 2. Controles verificados

| Control | Resultado |
|---|---|
| INICIAR / DETENER B (API + UI) | Presentes; token obligatorio |
| Estado persistido | `demo_state` / `active_state` |
| Runner activo | `demo-runner` + `active-runner` Up |
| Ciclos / última decisión | Expuestos en `/api/active/strategies` y diagnose |
| Protección posiciones al stop | Cancel BUY pending; exits protectivos se mantienen |
| Bloqueo compras si STOPPED | Motivo `bot_stopped_entries_blocked` |
| Auth sin token | HTTP 401 en POST start/stop |

## 3. Diagnóstico HOLD (API `/api/active/diagnose`)

Categorías humanas:

1. Ya existe una posición  
2. Tendencia no favorable  
3. Volatilidad insuficiente  
4. Costos demasiado elevados  
5. Riesgo excedido  
6. Señal no confirmada  
7. Datos no disponibles  
(+ Bot detenido)

**Denominador:** `unique_cycle_symbol` — un conteo por `(cycle_id, symbol)`. No trata filas repetidas del mismo ciclo+símbolo como muestras independientes. Se reporta aparte `entry_holds_unique` (excluye `hold_position`).

### Snapshot live (2026-11-10 ~15:13 UTC)

**A Conservadora** — HOLD únicos 1693 · entrada 630 · ciclos entrada 295

| Categoría | n | % |
|---|---:|---:|
| Ya existe una posición | 1063 | 62.79% |
| Señal no confirmada | 606 | 35.79% |
| Bot detenido | 24 | 1.42% |

**B Trading Activo** — HOLD únicos 1284 (100% bot detenido; sin compras porque permanece STOPPED)

Captura: `docs/screenshots/etapa-t1/01-estrategias.png`

## 4. Historial (API `/api/active/history`)

Por estrategia: compras/ventas reales, posiciones abiertas, rechazos, motivo humano, fecha/hora, precio virtual, comisiones, P/L realizado. Sin fills inventados. C permanece vacío por diseño.

## 5. Comparación económica (API `/api/active/compare`)

Campos: capital inicial, patrimonio proxy (cash + costo posiciones), resultado neto proxy, compras, ventas, cerradas, comisiones, exposición, drawdown proxy, ventana observada, frescura de datos.

**`declare_winner: false`** — no se declara ganadora por cantidad de operaciones ni con muestra desigual (B STOPPED / 0 trades).

## 6. Pruebas

```text
pytest tests/test_active_policy_b.py tests/test_active_diagnose_t1.py
→ 10 passed
```

Cubre: categorías HOLD, deduplicación ciclo+símbolo, flags B/C, start/stop idempotente sin tocar tablas demo.

## 7. Docker (post-rebuild T.1)

Servicios Up: `api`, `dashboard` (127.0.0.1:8088), `db` healthy, `demo-runner`, `active-runner`, `market-stream`, `trade-executor`, `worker`, `shadow-scheduler`.

## 8. Integridad de carteras

- Ledgers distintos: `demo_manual_control` ≠ `active_exp_v1`
- Cash A y B independientes; start/stop B no muta `demo_*`
- Sin suma de patrimonios en UI

## 9. Errores / pendientes

- Patrimonio compare usa **proxy** (cash + costo), no mark-to-market en vivo del endpoint compare (el overview de strategies sí intenta marks).
- B sin trades prospectivos hasta que el usuario autorice INICIAR.
- C sin ejecución hasta calibración.
- WSL/Docker puede colgarse en Windows; recuperación documentada aparte (reiniciar `WSLService`).

## 10. Checkpoint y rollback

| Artefacto | Valor |
|---|---|
| Tag pre | `checkpoint-etapa-t1-pre-20261110_100827` |
| Backup | `backups/paper_pre_etapa_t1_20261110_100827.dump` |
| Rollback código | `git checkout checkpoint-etapa-t1-pre-20261110_100827` |
| Rollback DB | `pg_restore` del dump (no borrar volúmenes) |

**No se alteraron** parámetros de entrada/salida para fabricar compras.
