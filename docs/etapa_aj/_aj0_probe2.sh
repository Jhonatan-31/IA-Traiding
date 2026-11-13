#!/usr/bin/env bash
set +e
echo "--- CRON ---"
crontab -l 2>/dev/null | grep ebz_backup
echo "--- BACKUPS ---"
ls -lah /srv/backups/ia-bot-trading 2>/dev/null | tail -n 12
echo "--- BACKUP LOGS ---"
ls -lah /srv/backups/ia-bot-trading/logs 2>/dev/null | tail -n 8
echo "--- CONSULTATE/EVS ---"
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-'
echo "--- SQL BOTS ---"
COMPOSE="docker compose -p ia-bot-trading -f /srv/apps/ia-bot-trading/deploy/ebz/docker-compose.yml --env-file /srv/apps/ia-bot-trading/.env"
$COMPOSE exec -T db psql -U paper -d paper -c "select id,status,mode from bots order by id;"
$COMPOSE exec -T db psql -U paper -d paper -c "select count(*) as fills from paper_fills;"
$COMPOSE exec -T db psql -U paper -d paper -c "select git_commit, deployed_at from deploy_meta where id=1;"
echo "--- FLAGS / PROSPECT ---"
$COMPOSE exec -T db psql -U paper -d paper -c "\dt" | head -n 40
$COMPOSE exec -T db psql -U paper -d paper -c "select * from prospect_runs order by id desc limit 3;" 2>/dev/null
$COMPOSE exec -T db psql -U paper -d paper -c "select key, value from kv_store where key ilike '%prospect%' or key ilike '%paper_ai%' or key ilike '%d28%' limit 20;" 2>/dev/null
$COMPOSE exec -T api printenv 2>/dev/null | grep -E 'PAPER|PROSPECT|DASHBOARD_READ|AI_' | sort
echo "=== FIN AJ0b ==="
