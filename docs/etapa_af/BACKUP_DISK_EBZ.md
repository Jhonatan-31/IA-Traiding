# Disco de backups EBZ (HITACHI)

**Fecha:** 2026-11-13  
**Dispositivo:** `/dev/sda2` (HITACHI HUA72302 ~1,8 TB)  
**Montaje:** `/srv/backups`  
**Label:** `EBZ-BACKUPS`  
**fstab:** UUID + `defaults,nofail`

## Áreas (independientes)

| Ruta | Proyecto | Contenido |
|------|----------|-----------|
| `/srv/backups/ia-bot-trading/` | AI Trading Bot Pro | `paper_ebz_*.dump` (PostgreSQL) |
| `/srv/backups/consultate/` | Consultate | `consultate_mysql_*.sql.gz` (MySQL) |

## Scripts

- Trading: `/srv/apps/ia-bot-trading/scripts/ebz_backup_paper.sh`
- Consultate: `/srv/backups/scripts/ebz_backup_consultate.sh`
- Setup disco: `scripts/ebz_setup_backup_disk.sh` (destructivo; solo una vez)

## Notas

- Este disco es **copia en el mismo servidor** (segundo medio físico). No sustituye backup off-site.
- EVS no usa este layout salvo autorización posterior.
- Retención por defecto: 14 dumps por área.
