# AG1 — Inventario de superficie de exposición (EBZ)

**Fecha:** 2026-11-13  
**Host:** EBZ · stack `ia-bot-trading`  
**Puerto publicado:** `0.0.0.0:8090` → dashboard nginx → API/market-stream internos

## Clasificación

| Recurso | Clase | Auth actual | Mutación | Riesgo |
|---------|-------|-------------|----------|--------|
| `/api/public/health` | PUBLIC HEALTH MINIMAL | Ninguna | No | Bajo |
| `/api/health` | INTERNO / healthcheck | Ninguna | No | Bajo (DB ok/paused) |
| `/api/system`, `/api/continuity`, `/api/reliability` | LECTURA SENSIBLE | Ninguna (auth AG preparada OFF) | No | Medio |
| `/api/overview`, `/positions`, `/trades`, `/risk` | LECTURA SENSIBLE | Ninguna (OFF) | No | Medio-Alto |
| `/api/demo|active|lab/*` POST | CONTROL ADMINISTRATIVO | `X-Lab-Token` | Sí | Alto si token filtra |
| `/api/express` POST | CONTROL | Token + ENDED | Rechazada | — |
| `/ws/` market-stream | LECTURA MERCADO PÚBLICO | Ninguna | No | Bajo (klines públicas) |
| PostgreSQL `5432` | INTERNO DEL SERVIDOR | Red Docker interna | — | No publicar host |
| OpenAPI `/docs` | DOCUMENTACIÓN | Ninguna si expuesta vía proxy | No | Medio (mapa de rutas) |

## Redes que alcanzan `:8090`

- LAN `192.168.1.0/24` (confirmado).
- Tailscale (si el host está en la tailnet) — sin Funnel.
- WAN router: **no autorizado / no abierto por esta etapa**.

## Conclusión

CORS no sustituye autenticación. La protección de mutaciones existe; la de **lectura sensible** está **preparada y desactivada** (`DASHBOARD_READ_AUTH=0`) hasta autorización de migración.
