# INFORME — Etapa AJ PRO

## VEREDICTO

**READY_FOR_APPROVAL**

La autenticación existente (AG/AH/AI) está lista para un procedimiento de activación productivo, verificable y reversible.  
**No se activó** Tailscale Serve para Trading, **no** se puso `DASHBOARD_READ_AUTH=1`, **no** se cambió firewall/bind.  
El dashboard **no** está protegido mientras la auth siga en `0`.

---

## ARQUITECTURA

| Elemento | Propuesta |
|----------|-----------|
| Ruta HTTPS | `https://servidor-ebz.tail528f82.ts.net:10000` (solo tailnet) |
| Puerto Serve | **10000** (no 443 Funnel EVS, no 8443 Consultate) |
| Proxy | Tailscale Serve → `http://127.0.0.1:8090` (nginx) |
| Cookies | `ib_read_session` HttpOnly · SameSite=Lax · Secure si HTTPS/`X-Forwarded-Proto` |
| Sesiones | Token de lectura en cookie; max_age `DASHBOARD_READ_SESSION_SECONDS` |
| Mutaciones | `X-Lab-Token` (separado; CSRF no depende de cookie de lectura) |
| Reglas | Sin Funnel Trading; ACL tailnet; health `/api/health` + `/api/public/*` |
| Vías alternativas hoy | `0.0.0.0:8090` LAN + IP Tailscale HTTP |
| Restricción futura (Fase D) | Bind `127.0.0.1:8090` **solo tras** B+C OK |
| Riesgos | Funnel EVS ya público (otro proyecto); CT logs del hostname; lectura abierta hasta Fase C; políticas Tailscale permisivas posibles |

Docs: `ARQUITECTURA_HTTPS.md`, `RUTAS_ALTERNATIVAS.md`, `GUIA_ACTIVACION_EBZ.md`.

---

## ACTIVACIÓN

Guía operativa exacta: **`docs/etapa_aj/GUIA_ACTIVACION_EBZ.md`**.

| Fase | Acción | Estado AJ |
|------|--------|-----------|
| A Preflight | SSH, health, Serve ajenos, backup, rollback | Ejecutable (script `aj_activation_preflight.sh`) |
| B HTTPS | `sudo tailscale serve --bg --https=10000 http://127.0.0.1:8090` | **Pendiente autorización** |
| C Auth | Token + `DASHBOARD_READ_AUTH=1` | **Pendiente autorización** |
| D Bind loopback | `127.0.0.1:8090:8080` | **Pendiente autorización** |
| E Postflight | Checklist seguridad/carteras | Tras B–D |

Rollback B: `sudo tailscale serve --https=10000 off` (sin `serve reset`).  
Rollback C: `DASHBOARD_READ_AUTH=0` + recreate api/dashboard.

---

## PRUEBAS

| | |
|--|--|
| Pasadas | 1–4, 6–12, 16–19 + regresión AF–AI (46) |
| Fallidas | 0 |
| Omitidas | 5 (expiración e2e), 13 (diseño), 14–15 (UI tras Serve) |
| Evidencia | `PRUEBAS_AJ.md`, `backend/tests/test_etapa_aj.py` |

---

## BACKUPS

| Ítem | Estado |
|------|--------|
| Cron | `0 0,12 * * *` + consultate `5 0,12` · America/Bogota · **sin cambios** |
| Primera auto 2026-11-14 00:00 Bogota | **PENDIENTE** (aún no ocurre) |
| Último válido | `paper_ebz_20261113_195855.dump` · sha256 OK · manifest OK |
| Integridad | `sha256sum -c` → OK · `backup_ebz.status=VERIFICADO` |
| Off-host | PREPARADO_SIN_ACTIVAR |

---

## CARTERAS

| Control | Estado |
|---------|--------|
| A (demo) | **STOPPED** |
| B (active) | **STOPPED** |
| PAPER_ONLY | **Sí** (`/api/system`, `/api/public/health`) |
| IA / PAPER_AI | OFF (sin activación en esta etapa) |
| Prospect | AB-PROSPECT-v1 **PREPARED_DISABLED** (sin cambio financiero) |
| D28H5 | Congelada · hash `5326edb8a539cfe5` intacto |
| Ledgers | Sin mutación AJ |
| Órdenes reales | Ninguna |

---

## SEGURIDAD

- Producción: `DASHBOARD_READ_AUTH=0`, `DASHBOARD_READ_TOKEN` vacío.  
- Trading **sin** Serve nuevo; **sin** Funnel Trading.  
- Funnel 443→3080 EVS y Serve 8443→8088 Consultate **intactos**.  
- Exposición WAN Trading: no introducida.  
- Lectura LAN `:8090` sigue abierta (esperado hasta autorización C/D).

---

## ENTREGA

| Artefacto | Valor |
|-----------|-------|
| Commit | `1237d00` |
| Tag | `checkpoint-etapa-aj` |
| Checkpoint pre | `checkpoint-etapa-aj-pre-20261113_154219` |
| Deploy previo EBZ | `e19e96f` (auth OFF; docs AJ no cambian acceso) |
| Backup | `paper_ebz_20261113_195855` (+ post-AJ al cerrar) |
| Docs | `docs/etapa_aj/*` |
| Rollback | por fase en guía; auth OFF sin pérdida AD–AI |

### Aprobaciones pendientes del usuario

1. ¿Ejecutar **Fase B** (Serve `:10000`)?  
2. ¿Ejecutar **Fase C** (`DASHBOARD_READ_AUTH=1` + token)?  
3. ¿Ejecutar **Fase D** (bind loopback)?  
4. ¿Autorizar off-host / monitor externo? (fuera de AJ)
