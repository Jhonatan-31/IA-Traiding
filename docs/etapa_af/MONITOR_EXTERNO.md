# AF5 — Supervisión externa independiente

## Problema

Si EBZ se apaga, el monitoreo alojado en EBZ también muere. Un segundo proceso en el mismo host no es independencia real.

## OPCIÓN A — Monitor en otro dispositivo de la tailnet (recomendada)

| Aspecto | Valor |
|---------|--------|
| Dependencia host EBZ | Baja (probe externo) |
| Internet público | No requerido si ambos en Tailscale |
| Seguridad | Tailscale ACL/grants; solo `/api/public/health` |
| Costo | Casi nulo (PC/móvil/VPS en tailnet) |
| Complejidad | Baja-media |
| Detección caída total | Sí |
| Notificación | Script local / toast / futuro webhook |

Diseño: cron/systemd en dispositivo B cada 60–120s → `curl https://…/api/public/health` o HTTP Tailscale → registrar fallo → alerta local.

## OPCIÓN B — Servicio externo de uptime

| Aspecto | Valor |
|---------|--------|
| Dependencia | Proveedor + Internet |
| Seguridad | Exponer endpoint sin datos sensibles; evitar Funnel |
| Costo | Freemium típico / de pago |
| Privacidad | Tercero ve latencia/uptime |
| Detección | Sí si hay ruta de red |

## Recomendación

**Opción A** (dispositivo Tailscale independiente + `/api/public/health`).

## Estado

**NOT_CONFIGURED** — no se instaló ni se modificó Tailscale. Requiere autorización explícita del usuario.
