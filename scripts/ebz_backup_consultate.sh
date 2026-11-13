#!/usr/bin/env bash
# Backup MySQL de Consultate en EBZ → /srv/backups/consultate (disco HITACHI).
# No toca ia-bot-trading ni EVS. No imprime secretos.
set -euo pipefail
OUT_DIR="${OUT_DIR:-/srv/backups/consultate}"
KEEP="${KEEP:-14}"
CONTAINER="${CONTAINER:-consultate-mysql}"
mkdir -p "$OUT_DIR"
if [[ ! -d "$OUT_DIR" ]]; then
  echo "ERROR: $OUT_DIR no existe (¿disco de backups montado?)" >&2
  exit 1
fi
if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "ERROR: contenedor $CONTAINER no encontrado" >&2
  exit 1
fi
TS=$(date -u +%Y%m%d_%H%M%S)
FILE="$OUT_DIR/consultate_mysql_${TS}.sql.gz"
# Credenciales desde el entorno del contenedor (no se ecoean).
docker exec "$CONTAINER" sh -c \
  'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --routines --triggers --no-tablespaces --databases "$MYSQL_DATABASE"' \
  | gzip -c > "$FILE"
# Retención
ls -1t "$OUT_DIR"/consultate_mysql_*.sql.gz 2>/dev/null | tail -n +"$((KEEP+1))" | xargs -r rm -f
echo "OK $FILE bytes=$(wc -c < "$FILE")"
