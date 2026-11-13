#!/usr/bin/env bash
# AF7 — Backup PostgreSQL del stack ia-bot-trading en EBZ (sin tocar Consultate/EVS).
# Uso en servidor:
#   bash /srv/apps/ia-bot-trading/scripts/ebz_backup_paper.sh
# Cron sugerido (autorizar aparte): 0 */6 * * * ...
set -euo pipefail
ROOT="${ROOT:-/srv/apps/ia-bot-trading}"
OUT_DIR="${OUT_DIR:-$ROOT/backups}"
KEEP="${KEEP:-14}"
COMPOSE="docker compose -p ia-bot-trading -f $ROOT/deploy/ebz/docker-compose.yml --env-file $ROOT/.env"
mkdir -p "$OUT_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
FILE="$OUT_DIR/paper_ebz_${TS}.dump"
$COMPOSE exec -T db pg_dump -U paper -d paper -Fc > "$FILE"
# Retención simple por cantidad de dumps
ls -1t "$OUT_DIR"/paper_ebz_*.dump 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
echo "OK $FILE bytes=$(wc -c < "$FILE")"
# Nota: copia fuera del host NO configurada (requiere autorización).
