#!/usr/bin/env bash
COMPOSE="docker compose -p ia-bot-trading -f /srv/apps/ia-bot-trading/deploy/ebz/docker-compose.yml --env-file /srv/apps/ia-bot-trading/.env"
$COMPOSE exec -T db psql -U paper -d paper -c "\dt"
echo "---"
$COMPOSE exec -T db psql -U paper -d paper -c "select tablename from pg_tables where schemaname='public' and (tablename ilike '%bot%' or tablename ilike '%lab%' or tablename ilike '%wallet%' or tablename ilike '%prospect%' or tablename ilike '%flag%' or tablename ilike '%backup%' or tablename ilike '%ledger%') order by 1;"
echo "--- ENV API ---"
$COMPOSE exec -T api printenv | grep -E 'PAPER|PROSPECT|DASHBOARD|LAB_|AI_|MODE' | sort
echo "--- SYSTEM ---"
curl -sS -m 5 http://127.0.0.1:8090/api/system | head -c 3000; echo
echo "--- OVERVIEW ---"
curl -sS -m 5 http://127.0.0.1:8090/api/overview 2>/dev/null | head -c 3000; echo
