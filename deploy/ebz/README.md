# Deploy EBZ — AI Trading Bot Pro (aislado)

Stack Docker **independiente** de Consultate y EVS.

| Recurso | Valor |
|---------|--------|
| Ruta servidor | `/srv/apps/ia-bot-trading` |
| Proyecto compose | `ia-bot-trading` |
| Dashboard | `http://192.168.1.12:8090` y Tailscale `:8090` |
| Postgres | solo red interna (sin puerto host) |

## Arranque rápido (en el servidor)

```bash
cd /srv/apps/ia-bot-trading
cp deploy/ebz/.env.ebz.example .env   # editar secretos
mkdir -p data/market_history
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env up -d --build
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml ps
```

## Desde Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy_trading_ebz.ps1
```

## Rollback (sin borrar datos)

```bash
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml stop
# o down SIN -v:
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml down
```

**Prohibido:** `down -v`, `docker volume prune`, `docker system prune`.

Documentación completa: [docs/DEPLOY_EBZ_TRADING.md](../../docs/DEPLOY_EBZ_TRADING.md)
