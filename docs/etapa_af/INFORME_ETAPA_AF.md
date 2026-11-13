# Etapa AF PRO — Informe final

**Fecha:** 2026-11-13  
**HEAD base AE:** `35ed6b1` / `a079f8a`  
**Commit AF:** (ver tag `checkpoint-etapa-af`; incluye sampler background + nginx DNS dinámico)  
**Checkpoint previo:** `checkpoint-etapa-af-pre-20261113_115320`  
**Backup local:** `backups/paper_pre_etapa_af_20261113_115320.dump`  
**Backup EBZ verificado:** `/srv/apps/ia-bot-trading/backups/paper_ebz_20261113_165854.dump` (167714 bytes)  
**AE/AD no reescritos.**

---

## A. VEREDICTO

**MONITOREO IMPLEMENTADO CON LIMITACIONES**

- IMPLEMENTADO / PROBADO / DESPLEGADO: SLI longitudinal, ventanas 24h/7d/30d, muestreo idempotente, `/api/reliability`, `/api/public/health`, panel UI, diseño monitor externo, auditoría seguridad, script backup EBZ.
- EVIDENCIA LONGITUDINAL: **EN ACUMULACIÓN** desde `measurements_started_at` ≈ `2026-11-13T16:58:23Z` (no inventada).
- DISPONIBILIDAD 30 DÍAS: **NO VERIFICADA** (aún no han trascurrido 30 días).
- Monitor externo: **NOT_CONFIGURED**.
- Limitaciones residuales: lectura dashboard sin auth en LAN; backup aún solo en disco del host; sin probe externo ante caída total EBZ.

---

## B. DISPONIBILIDAD

| Campo | Valor |
|-------|--------|
| Inicio mediciones | `2026-11-13T16:58:23.891559+00:00` |
| Período observado al cierre | Minutos / horas del mismo día |
| Cobertura 24h/7d/30d | `EVIDENCIA_EN_ACUMULACION` hasta llenar ventana |
| UNKNOWN | No cuenta como up (`unknown_not_counted_as_up=true`) |
| Uptime 30d | **No declarado** (evidencia insuficiente) |
| Limitación | Sin probe externo, caída total del host es invisible |

---

## C. SALUD EBZ (post-deploy AF)

api / dashboard / db / market-stream **healthy** · runners Up · A/B **STOPPED** · Consultate/EVS intactos · `dashboard_http=200` · `DEPLOY_GIT_COMMIT=a18d1e6…` · `/api/public/health` ok · external_monitor NOT_CONFIGURED.

---

## D. ALERTAS

CONT::* + continuity gaps preservados; muestreo no genera tormenta (1 sample/minuto, bucket idempotente). STOPPED autorizado no genera CRITICAL.

---

## E. SEGURIDAD

- Lectura LAN `:8090` sin auth: **riesgo documentado** (P1 residual) — ver `docs/etapa_af/SEGURIDAD_DASHBOARD.md`.
- `/api/public/health` sin saldos/posiciones/secretos.
- Sin cambios WAN / Tailscale / firewall.

---

## F. MONITOR EXTERNO

Opción A (Tailscale, otro dispositivo) **recomendada**. Estado: **NOT_CONFIGURED**. Detalle: `docs/etapa_af/MONITOR_EXTERNO.md`.

---

## G. BACKUPS

| Ámbito | Estado |
|--------|--------|
| Local pre-AF dump | OK |
| Restore aislado AE | Ya verificado |
| Script `scripts/ebz_backup_paper.sh` | OK (LF); primer dump EBZ 2026-11-13 16:58 UTC |
| Copia off-host independiente | **NO configurada** (riesgo residual) |
| Cron automático | **NO activado** (requiere autorización) |

---

## H. CARTERAS

A/B STOPPED · PAPER_ONLY · prospect disabled · EBZ paper limpio independiente del histórico local · sin órdenes reales.

---

## I. PRUEBAS

`test_etapa_af.py`: 5 passed. Regresiones AD/AE previas conservadas. Escenarios destructivos en prod EBZ: **NOT TESTED** (prohibidos).

---

## J. ENTREGA

| Ítem | Valor |
|------|--------|
| Commit | `a18d1e6` |
| Tag | `checkpoint-etapa-af` |
| Checkpoint previo | `checkpoint-etapa-af-pre-20261113_115320` |
| Push | OK |
| Deploy | `scripts/deploy_trading_ebz.ps1` OK |
| Dashboard | `http://192.168.1.12:8090` |
| Rollback | redeploy tag/commit pre-AF **sin** `down -v` / prune |

---

## K. PRÓXIMO PASO

1. Autorizar o no monitor externo Tailscale (Opción A).  
2. Activar cron de `ebz_backup_paper.sh` + decidir copia off-host.  
3. Acumular ≥24h/7d evidencia real.  
4. Solo después: seguridad de lectura / precios ejecutables / prospect — con autorización.
