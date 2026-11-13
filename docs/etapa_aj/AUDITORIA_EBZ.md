# AJ0 — Auditoría EBZ (solo lectura)

**Fecha:** 2026-11-13T20:46Z (probe SSH live)  
**Hostname:** `ebz`  
**Tailscale:** 1.104.5 · Host `servidor-ebz` · IP `100.107.168.61`  
**DNS:** `servidor-ebz.tail528f82.ts.net`

## Serve / Funnel existentes (NO tocar en AJ)

| Endpoint | Ámbito | Backend | Uso aparente |
|----------|--------|---------|--------------|
| `https://servidor-ebz…ts.net/` (443) | **Funnel ON (público)** | `127.0.0.1:3080` | EVS |
| `https://servidor-ebz…ts.net:8443/` | Tailnet only | `127.0.0.1:8088` | Consultate (Caddy) |

Advertencias:

- **Funnel ya está habilitado** en este nodo (EVS). No usar `tailscale serve reset` ni modificar `/` en 443.
- El nombre MagicDNS puede figurar en registros de transparencia de certificados por el Funnel/cert existentes.
- Capacidades del nodo incluyen `funnel` y puertos funnel `443,8443,10000`.

## AI Trading Bot Pro

| Ítem | Valor |
|------|--------|
| Dashboard | `0.0.0.0:8090` → nginx → API/WS |
| API publicada al host | No |
| `DASHBOARD_READ_AUTH` | `0` |
| Deploy commit | `e19e96f…` |

## Rutas alternativas de acceso (hoy)

1. `http://192.168.1.12:8090` (LAN) — lectura abierta.  
2. `http://100.107.168.61:8090` (Tailscale IP) — misma app HTTP.  
3. Futuro HTTPS privado propuesto: puerto **10000** (no ocupado; no choca con EVS/Consultate).

## Limpieza realizada

Contenedores huérfanos `ia-bot-ah-restore-*` eliminados (no productivos).
