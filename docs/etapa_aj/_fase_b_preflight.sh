#!/usr/bin/env bash
# Fase B — preflight + snapshot (solo lectura). No modifica nada.
set -euo pipefail
STAMP=$(date -u +%Y%m%d_%H%M%S)
SNAP_DIR="/tmp/aj_fase_b_snap_${STAMP}"
mkdir -p "$SNAP_DIR"
echo "SNAP_DIR=$SNAP_DIR"
echo "HOST=$(hostname) DATE=$(date -Is)"

echo "=== PREFLIGHT ==="
bash /srv/apps/ia-bot-trading/scripts/aj_activation_preflight.sh | tee "$SNAP_DIR/preflight.txt"

echo "=== SNAPSHOT SERVE/FUNNEL ==="
tailscale version | tee "$SNAP_DIR/tailscale_version.txt"
tailscale serve status --json 2>/dev/null | tee "$SNAP_DIR/serve_before.json" || true
tailscale serve status 2>/dev/null | tee "$SNAP_DIR/serve_before.txt" || true
tailscale funnel status 2>/dev/null | tee "$SNAP_DIR/funnel_before.txt" || true
tailscale status 2>/dev/null | tee "$SNAP_DIR/status_before.txt" || true

echo "=== LISTEN / DOCKER ==="
ss -tlnp 2>/dev/null | tee "$SNAP_DIR/listen_before.txt" || true
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | tee "$SNAP_DIR/docker_before.txt"

echo "=== CONSULATE / EVS PROBES ==="
curl -sS -m 5 -o /dev/null -w "evs_local_3080=%{http_code}\n" http://127.0.0.1:3080/ || echo "evs_local_3080=fail"
curl -sS -m 5 -o /dev/null -w "consultate_local_8088=%{http_code}\n" http://127.0.0.1:8088/ || echo "consultate_local_8088=fail"

echo "=== TRADING HEALTH / AUTH / BOTS ==="
curl -sS -m 5 http://127.0.0.1:8090/api/public/health | tee "$SNAP_DIR/public_health.json"; echo
curl -sS -m 5 http://127.0.0.1:8090/api/auth/status | tee "$SNAP_DIR/auth_status.json"; echo
COMPOSE="docker compose -p ia-bot-trading -f /srv/apps/ia-bot-trading/deploy/ebz/docker-compose.yml --env-file /srv/apps/ia-bot-trading/.env"
$COMPOSE exec -T db psql -U paper -d paper -tAc "select 'demo='||status from demo_state where id=1;" | tee "$SNAP_DIR/demo.txt"
$COMPOSE exec -T db psql -U paper -d paper -tAc "select 'active='||status from active_state where id=1;" | tee "$SNAP_DIR/active.txt"
$COMPOSE exec -T db psql -U paper -d paper -tAc "select 'deploy='||git_commit from deploy_meta where id=1;" | tee "$SNAP_DIR/deploy.txt"
grep -E '^(DASHBOARD_READ_AUTH|DEPLOY_GIT_COMMIT)=' /srv/apps/ia-bot-trading/.env | tee "$SNAP_DIR/env_flags.txt"

echo "=== PORT 10000 CHECK ==="
if ss -tlnp 2>/dev/null | grep -q ':10000'; then
  echo "PORT_10000=OCCUPIED"
  ss -tlnp | grep ':10000' || true
else
  echo "PORT_10000=FREE"
fi

echo "=== BACKUP LATEST ==="
ls -lah /srv/backups/ia-bot-trading | tail -n 8 | tee "$SNAP_DIR/backups_tail.txt"
cd /srv/backups/ia-bot-trading
LATEST=$(ls -1t paper_ebz_*.sha256 2>/dev/null | head -n1 || true)
if [[ -n "${LATEST:-}" ]]; then
  sha256sum -c "$LATEST" | tee "$SNAP_DIR/backup_sha.txt"
  cat "${LATEST%.sha256}.manifest.json" | tee "$SNAP_DIR/backup_manifest.json"
else
  echo "NO_SHA_FILE"
fi

echo "SNAP_DIR=$SNAP_DIR"
echo "=== PREFLIGHT DONE ==="
