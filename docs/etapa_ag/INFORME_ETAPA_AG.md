# Etapa AG PRO — Informe final

**Fecha:** 2026-11-13  
**Checkpoint previo:** `checkpoint-etapa-ag-pre-20261113_143948`  
**AF preservada.** Auth lectura **no** activada en producción.

---

## VEREDICTO

**SISTEMA PREPARADO CON ACTIVACIONES PENDIENTES**

---

## ACCESO

| Ítem | Estado |
|------|--------|
| Inventario rutas | `docs/etapa_ag/INVENTARIO_EXPOSICION.md` |
| Auth lectura | Código + middleware · `DASHBOARD_READ_AUTH=0` · **PREPARADO_SIN_ACTIVAR** |
| Token lectura | Distinto de `LAB_CONTROL_TOKEN` |
| Público | `/api/public/health`, `/api/health` |
| Mutaciones | Siguen con `X-Lab-Token` |
| Riesgo residual | Lectura sensible aún abierta en LAN/Tailscale hasta autorización |

## BACKUPS

| Ítem | Estado |
|------|--------|
| Script endurecido | Atómico + PGDMP + `pg_restore -l` + sha256 + manifest + `backup_runs` |
| Destino HITACHI | `/srv/backups/ia-bot-trading` **CONFIGURADO** (mismo host) |
| Cron | **ACTIVADO** (autorizado usuario): 00:00/12:00 America/Bogota |
| Off-host | **PREPARADO_SIN_ACTIVAR** (`ebz_backup_offhost.sh`) |
| Retención | 14 dumps |

## MONITOR EXTERNO

Cliente `scripts/external_monitor/probe_public_health.py` · **NOT_CONFIGURED**

## DISPONIBILIDAD (AF)

Inicio `2026-11-13T16:58:23Z` · evidencia en acumulación · 30d no verificada

## CARTERAS

A/B STOPPED · PAPER_ONLY · sin activación de estrategias en AG

## AUTORIZACIONES PENDIENTES

1. Activar `DASHBOARD_READ_AUTH` + token + migración UI.  
2. Destino off-host + sync.  
3. Instalar monitor en dispositivo independiente / ACL Tailscale.

## ENTREGA

Ver commit/tag `checkpoint-etapa-ag` tras deploy.
