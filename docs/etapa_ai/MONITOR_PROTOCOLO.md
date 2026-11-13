# AI7 — Protocolo de monitor independiente (no instalado)

Cliente: `scripts/external_monitor/probe_public_health.py`

## Procedimiento propuesto (dispositivo B en tailnet)

1. Cada 60–120 s: `python probe_public_health.py --url https://<ebz-serve>/api/public/health --state ./state.json`  
2. 2 fallos consecutivos → incidente activo.  
3. OK → resuelve incidente.  
4. Distinguir timeout / DNS / connection / HTTP.  
5. No usar tokens admin.

## Limitaciones actuales

- **NOT_CONFIGURED** en EBZ.  
- Sin probe externo no se demuestra detección de apagado total.  
- Fallo del dispositivo B ≠ caída de EBZ.

## Autorización necesaria

Instalar en segundo dispositivo + (opcional) ACL Tailscale al puerto/servicio HTTPS.
