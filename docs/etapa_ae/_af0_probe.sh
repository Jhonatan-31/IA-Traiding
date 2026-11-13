#!/usr/bin/env bash
set -euo pipefail
cd /srv/apps/ia-bot-trading
echo '=== AF0 EBZ SNAPSHOT ==='
hostname; date -u +%Y-%m-%dT%H:%M:%SZ
echo "deploy_commit=$(grep -E '^DEPLOY_GIT_COMMIT=' .env 2>/dev/null | cut -d= -f2- || echo unknown)"
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env ps
echo '--- inspect ---'
for c in $(docker ps -aq --filter name=ia-bot-trading); do
  docker inspect "$c" --format '{{.Name}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} restarts={{.RestartCount}} started={{.State.StartedAt}}'
done
echo '--- disk/mem ---'
df -h / | tail -1; free -h | head -2
echo '--- foreign ---'
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-' || true
echo '--- ledger ---'
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env exec -T db psql -U paper -d paper -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'demo' l, status, (SELECT cash::text FROM demo_accounts LIMIT 1) cash,
  (SELECT COUNT(*) FROM demo_positions) pos, (SELECT COUNT(*) FROM demo_trades) trades FROM demo_state WHERE id=1;
SELECT 'active' l, status, (SELECT cash::text FROM active_accounts LIMIT 1) cash,
  (SELECT COUNT(*) FROM active_positions) pos, (SELECT COUNT(*) FROM active_trades) trades FROM active_state WHERE id=1;
SELECT git_commit, deployed_at FROM deploy_meta WHERE id=1;
SQL
echo '--- backups on server ---'
ls -la /srv/apps/ia-bot-trading/backups 2>/dev/null || echo 'NO_SERVER_BACKUP_DIR'
ls -la ~/backups 2>/dev/null || echo 'NO_HOME_BACKUP_DIR'
echo '--- health ---'
curl -sS --max-time 15 http://127.0.0.1:8090/api/health || true
echo
curl -sS --max-time 20 http://127.0.0.1:8090/api/continuity 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); cc=d.get("continuity_center") or {}; print("overall",cc.get("overall")); print("deploy",cc.get("deploy")); print("alerts",len(d.get("critical_alerts") or []))' || true
