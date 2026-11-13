# AI6 — Recuperación off-host (no activada)

## Opciones

| Opción | Independencia | Costo | Complejidad | Privacidad |
|--------|---------------|-------|-------------|------------|
| **1. PC/NAS propio vía rsync/SSH** (recomendada) | Alta | Bajo | Baja | Alta |
| 2. Disco USB rotativo a otro equipo | Alta | Bajo | Media | Alta |
| 3. Object storage cifrado externo | Alta | Variable | Media | Depende proveedor |

## Recomendación principal

**Rsync/SSH diario** de `/srv/backups/ia-bot-trading` (+ consultate) a un equipo fuera de EBZ, con `OFFHOST_DEST` y script existente `ebz_backup_offhost.sh`.

## Alternativa

USB cifrado desconectado tras copia semanal.

## RPO/RTO (objetivos, no medidos post-desastre)

- RPO objetivo: ≤ 12 h (alineado a cron).  
- RTO objetivo stack paper: ≤ 4–8 h en host de reemplazo.  
- **Sin off-host verificado, pérdida total de EBZ puede perder NVMe + HITACHI juntos.**

## Estado

**PREPARADO_SIN_ACTIVAR** — requiere destino + autorización.
