# AG4 / AG6 — Off-host y monitor externo

## Off-host

| Nivel | Estado actual |
|-------|---------------|
| BACKUP EN EBZ (NVMe histórico + script) | CONFIGURADO |
| BACKUP segundo disco HITACHI `/srv/backups` | CONFIGURADO (mismo host) |
| BACKUP OFF-HOST | PREPARADO_SIN_ACTIVAR (`scripts/ebz_backup_offhost.sh`) |
| OFF-HOST VERIFICADO | No |
| RESTORE OFF-HOST VERIFICADO | No |

Activación: definir `OFFHOST_DEST` (rsync/SSH) + autorización explícita. Preferir cifrado en tránsito.

## Monitor externo

- Endpoint: `/api/public/health` (sin saldos/posiciones/secretos).
- Cliente: `scripts/external_monitor/probe_public_health.py`
- Dedup: 2 fallos consecutivos abren incidente; OK resuelve.
- Distingue timeout / DNS / HTTP / connection.
- **NOT_CONFIGURED** hasta instalarse fuera de EBZ.

Tailscale: ACL mínimo al puerto 8090; sin Funnel; sin token admin. Ver `docs/etapa_af/MONITOR_EXTERNO.md`.
