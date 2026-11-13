# AI2 — HTTPS privado (preparación, no aplicado)

## Comparación

| Opción | Seguridad | Complejidad | Cookies Secure | Notas |
|--------|-----------|-------------|----------------|-------|
| **A. Tailscale Serve** (recomendada) | Alta en tailnet | Baja | Sí | Sin Funnel; identidad de dispositivo |
| B. Nginx TLS propio | Alta | Media-Alta | Sí | Certificados/renovación manual o ACME interno |
| C. Solo HTTP LAN | Baja-Media | Nula | No | Estado actual `:8090` |

## Recomendación

**Opción A — Tailscale Serve** hacia `127.0.0.1:8090` (o bind dashboard a localhost + Serve).

Ejemplo (no secretos): `examples/tailscale_serve.example.json`.

## Requisitos antes de activar auth prod

1. HTTPS privado operativo.  
2. Login establece cookie con `Secure=true`.  
3. ACL: solo dispositivos autorizados al puerto/servicio.  
4. Sin Funnel / sin WAN.  
5. Rollback: desactivar Serve + `DASHBOARD_READ_AUTH=0`.

## Estado AI

**PREPARADO_SIN_ACTIVAR** — Tailscale CLI presente en EBZ; Serve **no** configurado por esta etapa.
