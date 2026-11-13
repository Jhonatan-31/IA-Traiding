# Etapa AF PRO — Informe final

**Fecha:** 2026-11-13  
**HEAD base:** `35ed6b1`  
**Checkpoint previo:** `checkpoint-etapa-af-pre-20261113_115320`  
**Backup local:** `backups/paper_pre_etapa_af_20261113_115320.dump`  
**AE/AD no reescritos.**

---

## A. VEREDICTO

**MONITOREO IMPLEMENTADO CON LIMITACIONES**

- IMPLEMENTADO / PROBADO / DESPLEGADO: SLI longitudinal, ventanas 24h/7d/30d, muestreo idempotente, `/api/reliability`, `/api/public/health`, panel UI, diseño monitor externo, auditoría seguridad, script backup EBZ.
- EVIDENCIA LONGITUDINAL: **EN ACUMULACIÓN** desde `measurements_started_at` (no inventada).
- DISPONIBILIDAD 30 DÍAS: **NO VERIFICADA** (aún no han trascurrido 30 días).
- Monitor externo: **NOT_CONFIGURED**.

---

## B. DISPONIBILIDAD

| Campo | Valor |
|-------|--------|
| Inicio mediciones | Al primer sample post-deploy AF (`reliability_meta.measurements_started_at`) |
| Período observado al cierre | Horas (mismo día) |
| Cobertura 24h/7d/30d | `EVIDENCIA_EN_ACUMULACION` hasta llenar ventana |
| UNKNOWN | No cuenta como up (`unknown_not_counted_as_up=true`) |
| Limitación | Sin probe externo, caída total del host es invisible |

---

## C. SALUD EBZ (AF0)

api/dashboard/db/market-stream healthy · runners Up · A/B STOPPED cash 1000/1000 pos 0 · Consultate/EVS intactos · disco 11% · deploy_commit AE previo `a079f8a` (actualizará en deploy AF).

---

## D. ALERTAS

CONT::* + continuity gaps preservados; muestreo no genera tormenta (1 sample/minuto). STOPPED autorizado no genera CRITICAL.

---

## E. SEGURIDAD

- Lectura LAN `:8090` sin auth: **riesgo documentado** (P1 residual).
- `/api/public/health` sin saldos/posiciones/secretos.
- Sin cambios WAN/Tailscale/firewall.

---

## F. MONITOR EXTERNO

Opción A (Tailscale otro dispositivo) **recomendada**. Estado: **NOT_CONFIGURED**.

---

## G. BACKUPS

| Ámbito | Estado |
|--------|--------|
| Local pre-AF dump | OK |
| Restore aislado AE | Ya verificado |
| Directorio backups **en EBZ** | **NO existía** (AF0) |
| Script `scripts/ebz_backup_paper.sh` | Implementado; copia off-host **no** configurada |

---

## H. CARTERAS

A/B STOPPED · PAPER_ONLY · prospect disabled · EBZ paper limpio independiente del histórico local · sin órdenes reales.

---

## I. PRUEBAS

Suite AF + AE + AD relevantes: ver ejecución en entrega. Escenarios destructivos en prod EBZ: **NOT TESTED** (prohibidos).

---

## J. ENTREGA

Commit/tag/push/deploy AF · checkpoint pre · rollback = redeploy pre-AF **sin** `-v`.

---

## K. PRÓXIMO PASO

1. Autorizar o no monitor externo Tailscale (Opción A).  
2. Activar cron de `ebz_backup_paper.sh` + decidir copia off-host.  
3. Acumular ≥24h/7d evidencia real.  
4. Solo después: seguridad de lectura / precios ejecutables / prospect — con autorización.
