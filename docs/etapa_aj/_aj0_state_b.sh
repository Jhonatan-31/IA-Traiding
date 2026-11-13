#!/usr/bin/env bash
COMPOSE="docker compose -p ia-bot-trading -f /srv/apps/ia-bot-trading/deploy/ebz/docker-compose.yml --env-file /srv/apps/ia-bot-trading/.env"
echo "ACTIVE:"; $COMPOSE exec -T db psql -U paper -d paper -tAc "select status from active_state where id=1;"
echo "ENGINE:"; $COMPOSE exec -T db psql -U paper -d paper -c "select * from engine_state;" 2>&1 | head -n 20
echo "DEPLOY:"; $COMPOSE exec -T db psql -U paper -d paper -tAc "select git_commit from deploy_meta where id=1;"
echo "BACKUPS:"; $COMPOSE exec -T db psql -U paper -d paper -c "select id,status,dump_path from backup_runs order by id desc limit 5;"
echo "PROSPECT:"; $COMPOSE exec -T db psql -U paper -d paper -c "select id,coalesce(status::text,''),coalesce(name,'') from prospect_experiments order by id desc limit 5;"
echo "PROTO:"; $COMPOSE exec -T db psql -U paper -d paper -c "select id,name,status from research_protocols order by id desc limit 8;"
echo "ENV:"; $COMPOSE exec -T api printenv | grep -E 'PAPER|PROSPECT|DASHBOARD|SHADOW|AI_' | sort
echo "SHA:"; cd /srv/backups/ia-bot-trading && sha256sum -c paper_ebz_20261113_195855.sha256; cat paper_ebz_20261113_195855.manifest.json; echo
curl -sS -m 5 http://127.0.0.1:8090/api/system | head -c 2000; echo
