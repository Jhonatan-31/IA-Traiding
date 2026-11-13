# AH6 / AH7 — Backups y off-host

## Cron (AG, preservado)

```
CRON_TZ=America/Bogota
0 0,12 * * * …/ebz_backup_paper.sh
5 0,12 * * * …/ebz_backup_consultate.sh
```

Servidor en UTC; cron interpreta horas en Bogota.

## Evidencia

| Tipo | Estado |
|------|--------|
| Entrada cron instalada | Sí |
| Log `cron.log` | Vacío / ausente → **aún no hay evidencia de corrida programada** |
| Dumps manuales HITACHI | Sí (p.ej. `paper_ebz_20261113_195855.dump` + sha256 + manifest) |
| Off-host | PREPARADO_SIN_ACTIVAR (`ebz_backup_offhost.sh` sin `OFFHOST_DEST`) |

No declarar “cron funciona” solo por la entrada: falta la primera ejecución 00:00/12:00 Bogota post-activación.

## Retención propuesta (no activada)

- 14 dumps recientes (actual).  
- Futuro escalonado: diarios 14d + semanales 8 + mensuales 6 — **requiere autorización** antes de borrar.

## HITACHI

Segundo disco **en el mismo host** → no es off-host.
