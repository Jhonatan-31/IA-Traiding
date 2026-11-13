# AG2 — Protección de lectura del dashboard

## Decisión de diseño

**Opción C (proporcional):**  
1. Controles de red Tailscale/ACL (futuro, autorización aparte).  
2. Auth de aplicación con token de **lectura** distinto del de mutación.

| Aspecto | Opción A (solo app) | Opción B (solo Tailscale) | C (recomendada) |
|---------|---------------------|---------------------------|------------------|
| Complejidad | Media | Media | Media |
| Defensa en profundidad | Media | Media | Alta |
| Compatibilidad EBZ | Alta | Requiere ACL | Alta si flag OFF |
| Riesgo lockout | Alto si se activa mal | Medio | Mitigado con flag |

## Mecanismo

- Header: `X-Dashboard-Read-Token`
- Env: `DASHBOARD_READ_TOKEN` (nunca en git)
- Flag: `DASHBOARD_READ_AUTH=0` por defecto → **PREPARADO_SIN_ACTIVAR**
- Mutaciones: siguen con `LAB_CONTROL_TOKEN` / `X-Lab-Token`
- `/api/public/health` y `/api/health` permanecen sin auth de lectura

## Plan de activación (requiere autorización)

1. Generar token largo aleatorio en EBZ `.env` (`DASHBOARD_READ_TOKEN`).
2. Probar con curl autenticado desde un cliente.
3. Actualizar frontend para enviar header (sesión/memoria; no localStorage permanente del token admin).
4. Poner `DASHBOARD_READ_AUTH=1` y redeploy.
5. Rollback: `DASHBOARD_READ_AUTH=0` + redeploy (sin `down -v`).

## Estado

**PREPARADO_SIN_ACTIVAR** en producción.
