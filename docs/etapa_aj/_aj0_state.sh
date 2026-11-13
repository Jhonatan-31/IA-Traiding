#!/usr/bin/env bash
COMPOSE="docker compose -p ia-bot-trading -f /srv/apps/ia-bot-trading/deploy/ebz/docker-compose.yml --env-file /srv/apps/ia-bot-trading/.env"
echo "--- DEMO STATE ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select * from demo_state;"
echo "--- ACTIVE STATE ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select * from active_state;"
echo "--- ENGINE ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select * from engine_state;"
echo "--- DEPLOY ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select * from deploy_meta;"
echo "--- BACKUP_RUNS ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select id, started_at, finished_at, status, dump_path from backup_runs order by id desc limit 5;"
echo "--- PROSPECT EXP ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select id, status, name from prospect_experiments order by id desc limit 5;"
echo "--- RESEARCH ---"
$COMPOSE exec -T db psql -U paper -d paper -c "select id, name, status, hash from research_protocols where name ilike '%D28%' or name ilike '%prospect%' order by id desc limit 10;"
echo "--- ENV ---"
$COMPOSE exec -T api printenv | grep -E 'PAPER|PROSPECT|DASHBOARD|LAB_|AI_|MODE|SHADOW' | sort
echo "--- SYSTEM ---"
curl -sS -m 5 http://127.0.0.1:8090/api/system; echo
echo "--- SHA256 latest ---"
cd /srv/backups/ia-bot-trading && sha256sum -c paper_ebz_20261113_195855.sha256 && cat paper_ebz_20261113_195855.manifest.json
