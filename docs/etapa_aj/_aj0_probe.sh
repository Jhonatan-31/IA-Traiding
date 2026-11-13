#!/usr/bin/env bash
# Solo lectura — no modifica Tailscale, .env ni compose.
set -euo pipefail
echo "HOST=$(hostname)"
echo "DATE=$(date -Is)"
tailscale version 2>/dev/null | head -n 2 || true
echo "--- SERVE ---"
tailscale serve status 2>/dev/null || true
echo "--- FUNNEL ---"
tailscale funnel status 2>/dev/null || true
echo "--- LISTEN ---"
ss -tlnp 2>/dev/null | grep -E ':8090|:10000|:443|:8443|:3080|:8088' || true
cd /srv/apps/ia-bot-trading
echo "--- ENV ---"
grep -E '^(DASHBOARD_READ_AUTH|DEPLOY_GIT_COMMIT|PAPER)=' .env || true
echo "--- HEALTH ---"
curl -sS -m 5 http://127.0.0.1:8090/api/public/health; echo
curl -sS -m 5 http://127.0.0.1:8090/api/auth/status; echo
echo "--- COMPOSE ---"
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env ps 2>/dev/null | head -n 20 || true
echo "--- BOTS / DEPLOY ---"
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env exec -T api \
  python -c "
from sqlalchemy import text
from app.db import SessionLocal
s=SessionLocal()
for q in [
  'select id, status, mode from bots order by id',
  'select count(*) as fills from paper_fills',
  'select git_commit from deploy_meta where id=1',
]:
  try:
    print(q, '->', [dict(r) for r in s.execute(text(q)).mappings().all()])
  except Exception as e:
    print(q, 'ERR', type(e).__name__, e)
s.close()
" 2>&1 | head -n 40 || true
echo "--- CRON ---"
crontab -l 2>/dev/null | grep ebz_backup || true
echo "--- BACKUPS ---"
ls -lah /srv/backups/ia-bot-trading 2>/dev/null | tail -n 10 || true
echo "--- CONSULTATE/EVS ---"
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-' || true
echo "=== FIN AJ0 ==="
