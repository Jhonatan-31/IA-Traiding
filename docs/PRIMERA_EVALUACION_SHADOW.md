# Primera evaluación prospectiva Shadow — verificación

Evidencia: **2026-11-04 ~00:08–00:10 UTC** · PAPER_ONLY · **sin forzar resoluciones**.

## Veredicto

**Todavía no existen resultados prospectivos resueltos.**  
`RESOLVED=0` · `outcomes=0` · `ready_now=0` · `sample_sufficient=false` · **no se declara estrategia rentable**.

El primer lote (vela 18:00 UTC del 3-nov) solo será elegible tras el **cierre** de la vela de salida `00:00–01:00` UTC → **ready_after = 2026-11-04 01:00 UTC** (~51 min después de esta auditoría).

---

## 1. Verificación temporal

| Campo | Valor |
|-------|-------|
| `NOW()` UTC | 2026-11-04 00:08:41Z |
| Lotes 18:00–23:00 UTC 3-nov | 6 × 5 símbolos = **30** decisiones |
| Horizonte | 6 barras **1h** |
| Criterio listo | reloj ≥ `candle_open + 7h` **y** vela `exit_open=entry+6h` **cerrada** en Binance |

Auditoría individual (`horizon_audit` + fetch klines): **any_ready=False** en las 30.  
Razón uniforme: `clock_before_ready_after_close` · `has_exit_closed=False` (la vela 00:00 UTC aún abierta a las 00:08).

### Calendario de readiness (por lote)

| Candle open (UTC) | exit_open | ready_after close | n | clock_past @00:08 |
|-------------------|-----------|-------------------|---|-------------------|
| 03-nov 18:00 | 04-nov 00:00 | **04-nov 01:00** | 5 | no |
| 03-nov 19:00 | 04-nov 01:00 | 04-nov 02:00 | 5 | no |
| 03-nov 20:00 | 04-nov 02:00 | 04-nov 03:00 | 5 | no |
| 03-nov 21:00 | 04-nov 03:00 | 04-nov 04:00 | 5 | no |
| 03-nov 22:00 | 04-nov 04:00 | 04-nov 05:00 | 5 | no |
| 03-nov 23:00 | 04-nov 05:00 | 04-nov 06:00 | 5 | no |

No se asume readiness solo por “haber pasado medianoche”.

---

## 2. Resoluciones / scheduler

| Estado | Count |
|--------|-------|
| PENDING | **30** |
| RESOLVED | **0** |
| INVALID | **0** |
| `prospect_outcomes` | **0** |
| Duplicados decisión UNIQUE | **0** |
| Duplicados outcome | **0** |

Último ciclo Shadow (#42): started 00:04:01Z · `ok=true` · `decisions_new=5` · `resolved=0` · `invalid=0` · `error=null`  
`shadow_scheduler_state`: status=OK · `resolve_errors=0` · `inference_errors=0` · model `v20261103T193950Z`

Razones de pendiente: horizonte incompleto / reloj antes de `ready_after` (no error de API).

Idempotencia: `apply_outcome` solo escribe si sigue `PENDING` + UNIQUE `decision_id` en outcomes → **máximo una resolución por decisión**.

---

## 3. Resultados predictivos

**Ninguna predicción resuelta.** Campos N/A:

símbolo · acción · probabilidad · precio inicial/final · retorno · neto hipotético · acierto · calidad · timestamp

Nota: señales SMA Shadow son **discretas BUY/HOLD** (probabilidad calibrada N/A salvo futuro ML).  
HOLD ≠ venta ≠ ganancia ejecutada. Métricas predictivas ≠ simulación económica de lab/SMA.

---

## 4. Lab Auto — ventas

| Tipo | Count |
|------|-------|
| Ventas orgánicas de estrategia | **0** |
| `demo_verification_sell` BTC | 1 (rPnL −0.1346) — **excluida** del rendimiento orgánico |

Inventario Lab abierto: BTCUSDT, SOLUSDT, ZECUSDT (coste 25 c/u) · cash ≈ 924.87 · sin nuevas ventas naturales en esta ventana.

---

## 5. Panel `/performance`

Actualizado (sin inventar): pending/resolved/invalid/outcomes · `ready_now` · `pending_reason_summary` · `seconds_until_first_ready` · `strategy_claim_allowed=false` · curvas observadas · downtime host sleep · cierres con flag demo.

---

## 6. Seguridad

PAPER_ONLY · PAPER_AI off · sin cambio de parámetros/balances · sin reconstrucción en downtime · volúmenes ajenos intactos.

---

## 7. Qué falta para la “primera resolución”

1. Esperar **≥ 2026-11-04 01:00 UTC**.
2. Confirmar por símbolo que existe vela 1h `open=00:00` **cerrada**.
3. Dejar que `shadow-scheduler` ejecute `resolve_pending` (ciclo ~300 s).
4. Releer `prospect_outcomes` + `/api/prospect/report` + `/api/performance/compare`.
5. Con n≪30 resueltas: reportar hechos; **no** optimizar ni declarar edge.

Script de auditoría (solo lectura): `backend/scripts/audit_shadow_horizons.py`.
