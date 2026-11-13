# Etapa AD PRO — Informe final

**Fecha:** 2026-11-13  
**Base:** `b93e564` (post AC + hallazgos F11–F15)  
**Checkpoint previo:** `checkpoint-etapa-ad-pre-20261113_110219`  
**Backups:** `backups/paper_pre_etapa_ad_*.dump` (no secretos en este informe)

---

## A. VEREDICTO

**P0 CORREGIDOS Y VERIFICADOS**

Con limitaciones residuales documentadas (F01 causa raíz no-OOM no determinista al nivel de host; F13 histórico no reescrito; F15 GET read-only permanece público).

---

## B. MATRIZ DE CORRECCIONES

| ID | Causa raíz | Cambio | Test | Estado | Riesgo residual |
|----|------------|--------|------|--------|-----------------|
| AC-F11 | Débito cash antes de posición + `ON CONFLICT DO NOTHING` sin rollback | `SAVEPOINT ad_buy_atomic` + `FOR UPDATE` + insert estricto en demo/active/express | `test_ad_atomic_buy_*` | CORREGIDO | SAVEPOINT depende de transacción abierta del ciclo |
| AC-F12 | Early-return si `B_EXECUTION_AUTHORIZED=False` bloqueaba salidas | Entradas gated; protecciones siempre evalúan | `test_ad_b_unauthorized_*`, AC remediated | CORREGIDO | SL/TP umbrales sin cambio; cobertura durante hueco host no afirmada |
| AC-F01 | Exit 137 simultáneo; `OOMKilled=false` → kill externo (host/Docker) | Rebuild + restart selectivo runners; estados STOPPED | inspect + logs post-restart | MITIGADO | Causa host no controlable desde app; posible reincidencia en suspend |
| AC-F13 | `estimate_fill_price` ya incluye fee; engines sumaban fee otra vez | Cash = `qty * px` all-in; fee solo reporting | `test_ad_fee_all_in_*` | CORREGIDO (forward) | Histórico no mutado; D28H5 motor distinto documentado |
| AC-F14 | Eviction arbitraria `set(sorted(...)[-n:])` | LRU `OrderedDict.popitem(last=False)` | `test_ad_trade_id_lru_*` | CORREGIDO | Dedupe en memoria por vela; no ledger (viz stream) |
| AC-F15 | Express sin token; superficie desigual | POST `/control` + `require_lab_token` (410 ENDED); GET anotado read-only | `test_ad_express_control_*` | MITIGADO | GET status/report siguen públicos (solo lectura, ENDED) |
| AC-F04 | Sin métrica unificada de huecos host | `ops/continuity.py` + components demo/active en `/api/system` + HealthPage | `test_ad_heartbeat_gap_*` | MITIGADO | No configura Windows; no afirma protección en hueco |

---

## C. RUNNERS

| Servicio | Estado inicial | Causa salida | Estado final | Health/Heartbeat |
|----------|----------------|--------------|--------------|------------------|
| demo-runner | Exited(137) ~2d | OOM=false; kill simultáneo (host/Docker) | Up; STOPPED; fills=0 | hb_fresh=true |
| active-runner | Exited(137) | idem | Up; STOPPED; fills=0 | hb_fresh=true |
| worker | Exited(137) | idem | Up | — |
| trade-executor | Exited(137) | idem | Up | — |
| shadow-scheduler | Exited(137) | idem | Up | — |
| express-runner | Exited(0) | ENDED por diseño (`restart: no`) | **No reiniciado** | — |
| api / dashboard / db / market-stream | Up | — | Up (recreados api/dashboard) | db healthy |

Procesos reiniciados: demo, active, worker, trade-executor, shadow, api, dashboard.  
No reiniciado: express-runner (ENDED).

---

## D. CONTABILIDAD (antes → después recovery)

| Ledger | Cash | Pos | Órdenes | Trades |
|--------|------|-----|---------|--------|
| demo | 990.805738755798740 → igual | 0→0 | 112→112 | 112→112 |
| active | 1000 → 1000 | 0→0 | 0→0 | 0→0 |

Invariantes: sin resets, sin fills nuevos en recovery, ledgers no mezclados, A/B STOPPED.

---

## E. SEGURIDAD

- A STOPPED, B STOPPED  
- PAPER_ONLY  
- PAPER_AI OFF (sin cambio)  
- D28H5 congelada (sin tocar)  
- AB-PROSPECT-v1 PREPARED_DISABLED  
- Sin órdenes reales  
- Express mutaciones requieren token y se rechazan (410)  
- Otros contenedores Docker ajenos no tocados  

---

## F. PRUEBAS

Suite consolidada (única ejecución): **65 passed**, 0 failed, 0 skipped (subset AA/AB/AC/AD + protecciones + market + aggregator + valuation + demo control + risk).

Nuevas críticas AD: atomic buy rollback/success, fee all-in, B auth split, LRU eviction, heartbeat gap, express control.

No sumar 27+6 de reportes previos como únicos.

---

## G. ENTREGA

- Tag etapa: `checkpoint-etapa-ad`  
- Checkpoint previo: `checkpoint-etapa-ad-pre-20261113_110219`  
- Docs: este informe  
- Rollback: `git checkout checkpoint-etapa-ad-pre-20261113_110219` + restore dump si hiciera falta  

---

## H. SIGUIENTE PASO

**Etapa AE — Continuidad host y reconciliación contable histórica (si aplica)**  
Priorizar: instrumentación durable ante suspend Windows/WSL2, alertas operativas, y (solo con revisión explícita) plan de corrección contable de fees históricos si el alcance lo justifica.  
No nuevas estrategias ni activación de A/B/prospect hasta que continuidad host esté aceptable.
