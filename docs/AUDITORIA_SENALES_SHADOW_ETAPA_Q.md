# Auditoría señales / Shadow gap / integridad + Etapa Q

Fecha evidencia: 2026-11-03 ~23:50 UTC · HEAD post-fix.

## 1. `signals=0` vs `signals_buy=1` — no es inconsistencia lógica

| Contador | Significado |
|----------|-------------|
| `signals_buy` / `signals_sell` | Decisiones BUY/SELL **detectadas** en el ciclo (cruces SMA en velas cerradas), aunque ya existan en DB |
| `signals` (log JSON anidado) | Filas **nuevas** insertadas en `lab_signals` (`created=True`) |
| `enqueued` | Órdenes **nuevas** en `lab_orders` |
| `duplicates` | Skips idempotentes (señal y/o orden ya existentes) |

Evidencia ciclo tipico post-fill SOL:

- `eval_sample`: SOLUSDT `decision=BUY`, `candle_ms=1793739600000`, `cross_state=golden`
- `lab_signals` id=5 y `lab_orders` id=7 FILLED ya existen para esa clave
- Resultado: `signals_buy=1`, `signals=0`, `enqueued=0`, `duplicates=2`

Dashboard (`AutoTradePage`): muestra BUY/SELL/HOLD desde `lab_cycles.signals_*` (=detecciones). Correcto. Ahora también aclara `signals_new` / dups.

## 2. Órdenes duplicadas (`duplicates=2`, `enqueued=0`)

Señal original: **SOLUSDT BUY** candle `1793739600000` (hora 21:00 UTC), fill 22:00:16 UTC.

Claves UNIQUE:

- señal: `(strategy, symbol, side, candle_ms)`
- orden: `(account_id, strategy, symbol, side, candle_ms)`

`duplicates=2` = 1 skip de señal + 1 skip de orden en el mismo símbolo (doble conteo de *skips*, no doble ejecución).

Verificación: `GROUP BY candle_ms,symbol,side HAVING COUNT(*)>1` → **0 filas** en `lab_orders` y `lab_signals`. Una sola FILLED SOL. **No se perdió la operación ni se ejecutó dos veces.**

## 3. Gap Shadow 22:48 → 23:33 UTC (~45 min)

| Evidencia | Valor |
|-----------|--------|
| Shadow ciclo DB #35 | finished 22:48:30Z |
| Shadow ciclo DB #36 | started 23:33:08Z · `gap_sec=2678` (~44.6 min) |
| Lab ciclo #33 → #34 | mismo `gap_sec=2678` (22:50 → 23:35) |
| `RestartCount` shadow | **0** · StartedAt 2026-11-03T20:35:28Z |
| Heartbeat persistido | `shadow_scheduler_state.status=OK`, cycle_count=40 post-reanudación |
| Event Viewer Windows | **Kernel-Power 42** sleep 22:51:26Z · **Power-Troubleshooter 1** wake 23:31:14Z (Power Button) · sync reloj +2377 s |

Conclusión: **no hay crash/restart del contenedor**. El hueco es la **suspensión del host Windows** (tapa/botón). Ambos schedulers (Shadow + Lab) se detuvieron juntos y reanudaron sin RestartCount. No se deduce caída solo del fragmento de logs.

## 4. Resoluciones Shadow

- SHADOW_LIVE: **25 PENDING, 0 RESOLVED**
- Horizonte: 6 barras 1h; `ready_after` = open + 7h
- Primer lote (candle 18:00 UTC): listo **2026-11-04 01:00 UTC**
- Lote 22:00 creado en ciclo 23:33: listo **2026-11-04 05:00 UTC**

**Correcto que aún no resuelvan** a ~23:50 UTC del 3-nov. No se adelantan resultados.

## 5. Integridad tres carteras (evidencia API 2026-11-03T23:59:15Z)

| Ledger | Cash | Pos. | Equity MTM | Fees | Notas |
|--------|------|------|------------|------|-------|
| SMA paper | 775 | 9 | 998.86 | est. 0.225 | uPnL -1.14 · DD max -0.081% · 9 BUY / 0 SELL |
| Lab auto | 924.87 | 3 BTC/SOL/ZEC | 999.19 | 0.125 | rPnL -0.135 · uPnL -0.675 · DD vs peak 0.081% · FILLED 5 / REJECTED 2 |
| research_sim | 1000 | 0 | 1000 | 0 | virt_accounts; Shadow no ejecuta |

Reconciliación: cash Lab + cost posiciones = 924.87+75 = 999.87 ≈ equity+uPnL+fees coherente con fills. Ledgers separados. PAPER_ONLY · `shadow_executing=false`.

## 6. Etapa Q (desplegado)

- `GET /api/performance/compare` — verificado en contenedor api
- Dashboard `/performance` (nav Rendimiento)
- AutoTrade: semántica BUY≠signals_new; dups idempotentes
- Contadores `duplicates_signal` / `duplicates_order` / `signals_new` en `lab_executor_state.meta_json.last_signals` (post rebuild trade-executor)

## Pruebas

`tests/test_lab_signal_counters.py` → **2 passed** (api container).

## Conservación

Volúmenes ajenos (`rilobot_*`, `chikas-app_*`, `postgres_data`, etc.) y contenedores detenidos de otros proyectos **intactos**. Solo recreados api / dashboard / trade-executor / market-stream del stack iabottraiding.
