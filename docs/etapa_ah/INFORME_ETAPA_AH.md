# Etapa AH PRO — Informe final

**Fecha:** 2026-11-13  
**Checkpoint previo:** `checkpoint-etapa-ah-pre-20261113_152057`  
**Base AG:** `bcb41a5` / tag `checkpoint-etapa-ag`

---

## A. VEREDICTO

**AUTENTICACIÓN PREPARADA Y VALIDADA EN AISLADO**

Producción permanece con `DASHBOARD_READ_AUTH=0`. No se activó lectura protegida.

---

## B. SEGURIDAD

- Middleware + cookie/header + `hmac.compare_digest`.  
- UI `AuthGate` solo si `enforced`.  
- Sin token en localStorage.  
- `/ws/market` = fan-out público (sin ledgers).  
- Mutaciones siguen con `X-Lab-Token`.  
- Riesgo residual: lectura abierta en LAN mientras auth OFF; HTTP sin Secure cookie hasta HTTPS privado.

## C. PRODUCCIÓN

`DASHBOARD_READ_AUTH=0` · dashboard usable · healthchecks sin credenciales admin.

## D. BACKUPS

| Ítem | Estado |
|------|--------|
| Cron | Activo 00:00/12:00 America/Bogota (preservado) |
| Evidencia cron.log | Pendiente (aún no hubo slot programado) |
| Dump validado | `paper_ebz_20261113_195855.dump` sha256 OK |
| Restore aislado AH | **OK** · 63 tablas · demo/active STOPPED · ~1s |
| Off-host | PREPARADO_SIN_ACTIVAR |
| HITACHI | Mismo host (no off-host) |

## E. CARTERAS

A/B STOPPED · PAPER_ONLY · sin cambios de estrategias.

## F. PRUEBAS

`test_etapa_ah.py` + `test_etapa_ag.py`: **17 passed**.

## G. ENTREGA

| Ítem | Valor |
|------|--------|
| Checkpoint previo | `checkpoint-etapa-ah-pre-20261113_152057` |
| Tag | `checkpoint-etapa-ah` |
| Auth prod | `DASHBOARD_READ_AUTH=0` |
| Rollback | poner `DASHBOARD_READ_AUTH=0` (no downgrade AD–AG) |

## H. ACTIVACIÓN FUTURA

Ver `PLAN_ACTIVACION.md` — **no ejecutar ahora**.
