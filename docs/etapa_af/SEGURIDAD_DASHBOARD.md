# AF6 — Auditoría de acceso del dashboard EBZ

## Hallazgo confirmado

- Dashboard escucha `0.0.0.0:8090` (LAN + Tailscale).
- Lectura sin autenticación de endpoints como `/api/system`, `/api/overview`, `/api/positions`, `/api/trades`, `/api/risk`, `/api/continuity`, `/api/reliability`.
- Mutaciones lab/demo/active requieren `X-Lab-Token` (ya existente).
- Express mutaciones: token + 410 ENDED.

## Clasificación de datos

| Clase | Ejemplos | Riesgo en LAN/Tailscale |
|-------|----------|-------------------------|
| Pública mínima | `/api/public/health` (ok/db/mode/commit) | Bajo |
| Operativa sensible | saldos, posiciones, trades, risk | Medio-Alto si red no confiable |
| Administrativa | start/stop bots | Protegida por token |

**No se asume que IP privada = autenticación.**

## Plan (sin cambios WAN / Tailscale no autorizados)

1. Mantener mutaciones con `LAB_CONTROL_TOKEN`.
2. Usar `/api/public/health` para probes externos futuros.
3. Opcional futuro (requiere autorización): bind `127.0.0.1:8090` + Tailscale Serve, o auth de lectura.
4. No Funnel / no puertos router.

## Estado AF

- Endpoint público mínimo **implementado**.
- Restricción de lectura sensible: **documentada, no forzada** (evitar romper acceso del usuario).
- Sin secretos en el endpoint público.
