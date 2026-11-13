#!/usr/bin/env bash
# AG3 — Backup PostgreSQL ia-bot-trading en EBZ (atómico + checksum + manifest).
# Destino: /srv/backups/ia-bot-trading (HITACHI) si existe; si no, $ROOT/backups.
# Cron (autorizado): CRON_TZ=America/Bogota → 0 0,12 * * *
set -euo pipefail
ROOT="${ROOT:-/srv/apps/ia-bot-trading}"
if [[ -d /srv/backups/ia-bot-trading ]]; then
  OUT_DIR="${OUT_DIR:-/srv/backups/ia-bot-trading}"
else
  OUT_DIR="${OUT_DIR:-$ROOT/backups}"
fi
KEEP="${KEEP:-14}"
MIN_BYTES="${MIN_BYTES:-1024}"
COMPOSE="docker compose -p ia-bot-trading -f $ROOT/deploy/ebz/docker-compose.yml --env-file $ROOT/.env"
DB_CTR="${DB_CTR:-ia-bot-trading-db-1}"
mkdir -p "$OUT_DIR"
TS=$(date -u +%Y%m%d_%H%M%S)
BASE="paper_ebz_${TS}"
TMP="$OUT_DIR/.${BASE}.dump.partial"
FINAL="$OUT_DIR/${BASE}.dump"
MANIFEST="$OUT_DIR/${BASE}.manifest.json"
SHAFILE="$OUT_DIR/${BASE}.sha256"

cleanup_partial() { rm -f "$TMP" 2>/dev/null || true; }
trap cleanup_partial EXIT

AVAIL_KB=$(df -Pk "$OUT_DIR" | awk 'NR==2{print $4}')
if [[ -n "${AVAIL_KB:-}" && "$AVAIL_KB" -lt 102400 ]]; then
  echo "ERROR: espacio insuficiente en $OUT_DIR (${AVAIL_KB}KB)" >&2
  exit 2
fi

GIT_COMMIT=$(grep -E '^DEPLOY_GIT_COMMIT=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)
PG_VER=$($COMPOSE exec -T db psql -U paper -d paper -tAc "SHOW server_version;" | tr -d '[:space:]' || echo unknown)

$COMPOSE exec -T db pg_dump -U paper -d paper -Fc > "$TMP"
BYTES=$(wc -c < "$TMP" | tr -d ' ')
if [[ "$BYTES" -lt "$MIN_BYTES" ]]; then
  echo "ERROR: dump demasiado pequeño ($BYTES < $MIN_BYTES)" >&2
  exit 3
fi

# Magic header custom dump
HEAD_HEX=$(head -c 5 "$TMP" | od -An -tx1 | tr -d ' \n')
if [[ "$HEAD_HEX" != "5047444d50" ]]; then
  echo "ERROR: firma PGDMP inválida" >&2
  exit 4
fi

VALIDATE_NOTE="pgdmp_magic_ok"
# List TOC inside running db container (non-destructive)
docker cp "$TMP" "$DB_CTR:/tmp/ag_backup_check.dump"
if docker exec "$DB_CTR" pg_restore -l /tmp/ag_backup_check.dump >/tmp/ag_backup_toc.txt 2>/tmp/ag_backup_toc.err; then
  TOC_LINES=$(wc -l < /tmp/ag_backup_toc.txt | tr -d ' ')
  if [[ "$TOC_LINES" -lt 5 ]]; then
    echo "ERROR: TOC demasiado corto ($TOC_LINES)" >&2
    exit 5
  fi
  VALIDATE_NOTE="pg_restore_list_ok lines=$TOC_LINES"
else
  echo "ERROR: pg_restore -l falló" >&2
  cat /tmp/ag_backup_toc.err >&2 || true
  exit 5
fi
docker exec "$DB_CTR" rm -f /tmp/ag_backup_check.dump || true

SHA=$(sha256sum "$TMP" | awk '{print $1}')
mv -f "$TMP" "$FINAL"
trap - EXIT
printf '%s  %s\n' "$SHA" "$(basename "$FINAL")" > "$SHAFILE"

python3 - <<PY
import json, pathlib
manifest = {
  "created_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "scope": "ia-bot-trading-paper",
  "database": "paper",
  "format": "custom(-Fc)",
  "path": "$FINAL",
  "bytes": int("$BYTES"),
  "sha256": "$SHA",
  "git_commit": """${GIT_COMMIT:-}""",
  "pg_version": """${PG_VER:-}""",
  "validation": """${VALIDATE_NOTE}""",
  "status": "OK",
}
pathlib.Path("$MANIFEST").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("manifest_ok")
PY

$COMPOSE exec -T db psql -U paper -d paper -v ON_ERROR_STOP=1 <<SQL >/dev/null || true
CREATE TABLE IF NOT EXISTS backup_runs(
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  scope TEXT NOT NULL,
  path TEXT,
  bytes BIGINT,
  sha256 TEXT,
  git_commit TEXT,
  pg_version TEXT,
  status TEXT NOT NULL,
  detail_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
INSERT INTO backup_runs(scope, path, bytes, sha256, git_commit, pg_version, status, detail_json)
VALUES (
  'ia-bot-trading-paper',
  '$FINAL',
  $BYTES,
  '$SHA',
  '${GIT_COMMIT:-}',
  '${PG_VER:-}',
  'OK',
  '{"validation":"${VALIDATE_NOTE}"}'::jsonb
);
SQL

mapfile -t OLD < <(ls -1t "$OUT_DIR"/paper_ebz_*.dump 2>/dev/null | tail -n +"$((KEEP+1))" || true)
for f in "${OLD[@]:-}"; do
  [[ -z "${f:-}" ]] && continue
  rm -f "$f" "${f%.dump}.manifest.json" "${f%.dump}.sha256"
done

echo "OK $FINAL bytes=$BYTES sha256=$SHA validation=${VALIDATE_NOTE}"
