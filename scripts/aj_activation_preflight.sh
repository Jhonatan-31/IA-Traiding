#!/usr/bin/env bash
# AJ Fase A — preflight solo lectura. NO modifica Tailscale, .env ni compose.
set -euo pipefail

echo "=== AJ preflight $(date -Is) ==="
echo "--- Tailscale ---"
tailscale version | head -n 2 || true
tailscale status --self 2>/dev/null | head -n 5 || true
echo "--- Serve / Funnel (no modificar) ---"
tailscale serve status 2>/dev/null || true
tailscale funnel status 2>/dev/null || true
echo "--- Listeners ---"
ss -tlnp 2>/dev/null | grep -E ':8090|:10000|:443|:8443|:3080|:8088' || true
echo "--- Trading env (flags only) ---"
cd /srv/apps/ia-bot-trading 2>/dev/null || { echo "MISSING_APP_DIR"; exit 1; }
grep -E '^(DASHBOARD_READ_AUTH|DEPLOY_GIT_COMMIT|PAPER)=' .env 2>/dev/null || true
echo "--- Compose ps ---"
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env ps 2>/dev/null || true
echo "--- Public health ---"
curl -sS -m 5 http://127.0.0.1:8090/api/public/health || true
echo
echo "--- Auth status ---"
curl -sS -m 5 http://127.0.0.1:8090/api/auth/status || true
echo
echo "--- Cron backups ---"
crontab -l 2>/dev/null | grep -E 'ebz_backup' || echo '(no cron match)'
echo "--- Latest backup files ---"
ls -lah /srv/backups/ia-bot-trading 2>/dev/null | tail -n 8 || true
echo "=== FIN preflight (sin cambios) ==="
