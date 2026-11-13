# Etapa AE PRO — Informe final

**Fecha:** 2026-11-13  
**HEAD base:** `78be72d`  
**Checkpoint previo:** `checkpoint-etapa-ae-pre-20261113_113815`  
**Backup local:** `backups/paper_pre_etapa_ae_20261113_113815.dump`  
**AD no reescrito.**

---

## A. VEREDICTO

**CONTINUIDAD MEJORADA CON LIMITACIONES**

- IMPLEMENTADO: healthchecks Docker (api/ms/dashboard), centro de continuidad, estados de protección, eventos de hueco, política de autorrecuperación documentada, alertas de continuidad, panel UI, restore aislado, redeploy-safe script.
- VERIFICADO EN PRUEBA: suite AE + AD/AC/AB/AA (48 passed en subset); restore aislado OK (~1.4s restore / ~7s total).
- VERIFICADO EN PRODUCCIÓN (snapshot): stack EBZ Up, PAPER_ONLY, A/B STOPPED.
- PENDIENTE DE OBSERVACIÓN: continuidad longitudinal 24/7 (horas ≠ meses); watchdog externo no configurado.

---

## B. ESTADO EBZ

| Servicio | Inicial AE0 | Final (post-deploy AE) | Healthcheck | Heartbeat app |
|----------|-------------|------------------------|-------------|---------------|
| db | Up healthy | Up healthy | pg_isready | — |
| api | Up health=none | healthcheck HTTP `/api/health` | app | system |
| market-stream | Up health=none | healthcheck `/health` | hub metrics | — |
| dashboard | Up :8090 | healthcheck wget `/` | — | — |
| demo-runner | Up unless-stopped | Up | none (app heartbeat) | fresco STOPPED |
| active-runner | Up | Up | none (app heartbeat) | fresco STOPPED |
| worker / shadow / trade-executor | Up | Up | none | vía DB/scans |
| consultate / evs | Up | **intactos** | — | — |

Host: Ubuntu 26.04 nativo, Docker 29.9.2, 14Gi RAM, disco 11%.

---

## C. RECUPERACIÓN

| Escenario | Resultado |
|-----------|----------|
| unless-stopped crash container | Documentado como safe_automatic |
| Hueco heartbeat | Persistido en `continuity_gap_events` |
| Posiciones + gap crítico | `PROTECTION_UNAVAILABLE` + alerta CRITICAL |
| Host completo caído | **No detectable** desde el mismo host — requiere probe externo (NOT_CONFIGURED) |
| Fallas deliberadas en prod EBZ | **No ejecutadas** (restricción) |

Riesgo residual: sin monitor externo; reinicios Docker no curan disco lleno / volumen corrupto.

---

## D. CONTABILIDAD

### Local (backup AE)
Dump restaurado aislado: demo/active STOPPED; 69 tablas públicas; sin mutar operativo.

### EBZ (ledger paper limpio del deploy)
demo cash 1000 / pos 0; active cash 1000 / pos 0 — independiente del histórico local. Sin compras por AE.

---

## E. SEGURIDAD

A/B STOPPED · PAPER_ONLY · PAPER_AI OFF · D28H5 intacta · prospect disabled · sin órdenes reales · Consultate/EVS intactos.  
Hallazgo P1: dashboard `0.0.0.0:8090` lectura sin auth en LAN/Tailscale (no Internet router). Mitigación documentada; no abrir firewall WAN.

---

## F. OBSERVABILIDAD

- `/api/system` → `continuity_center`, `auto_recovery_policy`, `critical_alerts`
- `/api/continuity`
- HealthPage → Centro de salud y continuidad (entradas vs protección, deploy commit, gaps)
- Alertas `CONT::*` con dedupe/resolve

---

## G. BACKUPS

| Ítem | Resultado |
|------|----------|
| Pre-AE local dump | 1046989 bytes |
| Restore aislado | OK, restore_wall_ms≈1392, TOTAL_MS≈6940 |
| RPO/RTO | No inventados; restore prueba ~7s contenedor efímero |
| EBZ volume | preservado (no down -v) |

---

## H. TESTING

Subset AE+AD+AC+AB+AA+protecciones+aggregator: **48 passed**, 0 failed.  
NOT TESTED en prod: caídas forzadas de Postgres/WS EBZ; soak 24/7 longitudinal.

---

## I. DEPLOY

Flujo: cambio → commit → push → `scripts/deploy_trading_ebz.ps1` (ahora tolerante a :8090 propio).  
Rollback: redeploy commit previo **sin** `down -v`; no volver a borrar AD.

---

## J. SIGUIENTE ETAPA

**AF — Observación longitudinal + probe externo opcional (Tailscale)**  
Sin nuevas estrategias hasta acumular evidencia de uptime y decidir si se autoriza healthcheck externo.
