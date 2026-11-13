#!/usr/bin/env bash
set -euo pipefail
echo '=== AE0 HOST ==='
hostname
uname -a
cat /etc/os-release | head -8
echo "uptime=$(uptime -s) now=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo '=== DOCKER ==='
docker version --format 'Client={{.Client.Version}} Server={{.Server.Version}}' 2>/dev/null || docker version | head -20
docker compose version 2>/dev/null || true
echo
echo '=== RESOURCES ==='
free -h | head -5
df -h / | tail -1
nproc
echo
echo '=== IA-BOT STACK ==='
cd /srv/apps/ia-bot-trading
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env ps
echo
echo '=== RESTART POLICY / HEALTH / RESTARTS ==='
for c in $(docker ps -aq --filter name=ia-bot-trading); do
  docker inspect "$c" --format '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}} oom={{.State.OOMKilled}} restarts={{.RestartCount}} started={{.State.StartedAt}}'
done
echo
echo '=== PORTS / NETWORKS / VOLUMES ==='
ss -tlnp | grep -E ':(8090|3000|3080|3081|3082|3307|3308|8088)\s' || true
docker network ls | grep -E 'ia-bot|consultate|evs'
docker volume ls | grep -E 'ia-bot|consultate|evs'
echo
echo '=== OTHER STACKS ==='
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-' || true
echo
echo '=== POSTGRES (ia-bot) ==='
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env exec -T db psql -U paper -d paper -c "SELECT version();" | head -3
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env exec -T db psql -U paper -d paper -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'demo' AS ledger, (SELECT status FROM demo_state WHERE id=1) AS status,
  (SELECT cash::text FROM demo_accounts LIMIT 1) AS cash,
  (SELECT COUNT(*)::text FROM demo_positions) AS positions,
  (SELECT COUNT(*)::text FROM demo_orders) AS orders,
  (SELECT COUNT(*)::text FROM demo_trades) AS trades,
  (SELECT heartbeat_at::text FROM demo_state WHERE id=1) AS heartbeat;
SELECT 'active' AS ledger, (SELECT status FROM active_state WHERE id=1) AS status,
  (SELECT cash::text FROM active_accounts LIMIT 1) AS cash,
  (SELECT COUNT(*)::text FROM active_positions) AS positions,
  (SELECT COUNT(*)::text FROM active_orders) AS orders,
  (SELECT COUNT(*)::text FROM active_trades) AS trades,
  (SELECT heartbeat_at::text FROM active_state WHERE id=1) AS heartbeat;
SELECT 'lab' AS ledger,
  COALESCE((SELECT status FROM lab_state WHERE id=1),'?') AS status,
  COALESCE((SELECT COUNT(*)::text FROM lab_positions),'0') AS positions;
SELECT 'express' AS ledger,
  COALESCE((SELECT status FROM express_state WHERE id=1),'?') AS status,
  COALESCE((SELECT COUNT(*)::text FROM express_positions),'0') AS positions;
SQL
echo
echo '=== API SYSTEM SNIPPET ==='
curl -sS --max-time 20 http://127.0.0.1:8090/api/health || true
echo
curl -sS --max-time 25 http://127.0.0.1:8090/api/system | python3 - <<'PY'
import sys,json
d=json.load(sys.stdin)
print('mode', d.get('mode'))
print('checked_at', d.get('checked_at'))
for k,v in (d.get('components') or {}).items():
    print(f"comp {k}: {v.get('status')}")
print('continuity', d.get('continuity'))
print('critical_alerts', d.get('critical_alerts'))
PY
echo
echo '=== MARKET STREAM (via dashboard proxy if any) ==='
curl -sS --max-time 10 http://127.0.0.1:8090/api/market/health 2>/dev/null || curl -sS --max-time 10 http://127.0.0.1:8090/api/market/status 2>/dev/null || echo 'no market health endpoint'
echo
echo '=== DISK LOGS TAIL ==='
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env logs --tail 3 demo-runner active-runner api 2>&1 | tail -40
