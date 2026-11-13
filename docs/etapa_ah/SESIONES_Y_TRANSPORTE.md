# AH2 — Sesiones y transporte

## Situación

Dashboard EBZ sirve por **HTTP** en `http://192.168.1.12:8090` (LAN/Tailscale).  
No hay HTTPS de origen en ese puerto hoy.

## Recomendación

| Modalidad | Usar ahora | Motivo |
|-----------|------------|--------|
| Cookie `Secure` + HTTPS | **Objetivo de activación** | Evita robo de cookie en tránsito |
| Tailscale Serve HTTPS privado | **Recomendado antes de ON** | HTTPS sin abrir WAN / sin Funnel |
| Cookie HttpOnly + SameSite=Lax **sin** Secure | Interim solo en red de confianza | Funciona en HTTP; no es ideal |
| Token en `localStorage` | **No** | Persistente y legible por XSS |
| Token en query string | **No** | Logs, historial, capturas |

## Implementación AH

- Login: `POST /api/auth/login` → cookie HttpOnly `ib_read_session`.
- `Secure=true` solo si la petición es HTTPS / `X-Forwarded-Proto: https`.
- Header `X-Dashboard-Read-Token` sigue válido (automatización / pruebas).
- Frontend **no** guarda el token; solo envía `credentials: include`.
- Mutaciones: `X-Lab-Token` separado (no fusionado).

## Activación segura (futura)

1. Habilitar Tailscale Serve (u otro HTTPS privado) **con autorización**.
2. Confirmar cookie Secure en login.
3. Luego `DASHBOARD_READ_AUTH=1`.
