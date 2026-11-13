#!/usr/bin/env bash
# AF7 — Backup PostgreSQL del stack ia-bot-trading en EBZ (sin tocar Consultate/EVS).
# Destino preferido: disco HITACHI montado en /srv/backups/ia-bot-trading
# Uso:
#   bash /srv/apps/ia-bot-trading/scripts/ebz_backup_paper.sh
# Cron: 0 0,12 * * * (00:00 y 12:00 hora local EBZ)
set -euo pipefail
ROOT="${ROOT:-/srv/apps/ia-bot-trading}"
if [[ -d /srv/backups/ia-bot-trading ]]; then
  OUT_DIR="${OUT_DIR:-/srv/backups/ia-bot-trading}"
else
  OUT_DIR="${OUT_DIR:-$ROOT/backups}"
fi
KEEP="${KEEP:-14}"
COMPOSE="docker compose -p ia-bot-trading -f $ROOT/deploy/ebz/docker-compose.yml --env-file $ROOT/.env"
mkdir -p "$OUT_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
FILE="$OUT_DIR/paper_ebz_${TS}.dump"
$COMPOSE exec -T db pg_dump -U paper -d paper -Fc > "$FILE"
ls -1t "$OUT_DIR"/paper_ebz_*.dump 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
echo "OK $FILE bytes=$(wc -c < "$FILE")"
