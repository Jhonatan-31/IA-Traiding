# Despliegue AI Trading Bot Pro en servidor EBZ

**Objetivo:** PAPER_ONLY 24/7, aislado de Consultate y EVS.  
**Host:** `adminebz@192.168.1.12` (SSH alias `consultate`)  
**Ruta:** `/srv/apps/ia-bot-trading`  
**Dashboard:** `http://192.168.1.12:8090` y `http://<tailscale-ip>:8090`

## Aislamiento

| Este stack | No tocar |
|------------|----------|
| Proyecto `ia-bot-trading` | `consultate`, `evs-bienestar-pastoral` |
| Red `ia-bot-trading_default` | `consultate_default`, `evs_*` |
| Volúmenes `ia-bot-trading_*` | `consultate_*`, `evs-*` |
| Puerto host **8090** | 3000, 3080–3082, 3307–3308, 8088 |

Prohibido en el host compartido:

- `docker compose down -v`
- `docker volume prune`
- `docker system prune`
- Modificar `~/consultate` o `/srv/apps/EVS-bienestar-pastoral`

## Preflight

```bash
ssh consultate
ss -tlnp | grep 8090 || echo "8090 libre OK"
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'consultate-|evs-'
```

## Despliegue

### Opción A — script Windows

Desde la raíz del repo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/deploy_trading_ebz.ps1
```

### Opción B — manual

1. Crear directorio y sincronizar código (sin `.env` local con secretos).
2. En servidor:

```bash
cd /srv/apps/ia-bot-trading
cp deploy/ebz/.env.ebz.example .env
# Editar DB_PASSWORD y LAB_CONTROL_TOKEN (fuertes, únicos)
mkdir -p data/market_history
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env up -d --build
```

## Postflight

```bash
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml ps
docker ps --format '{{.Names}}' | grep -E 'consultate-|evs-'   # deben seguir Up
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/
curl -sS http://127.0.0.1:8090/api/system | head -c 400
```

Esperado:

- Contenedores `ia-bot-trading-*` Up
- Consultate/EVS intactos
- `mode: PAPER_ONLY`
- demo/active en STOPPED (sin compras nuevas)
- Base PAPER limpia (sin migrar dump local)

## Servicios incluidos

`db`, `api`, `worker`, `market-stream`, `dashboard`, `shadow-scheduler`, `trade-executor`, `demo-runner`, `active-runner`

No incluidos por diseño: `express-runner` (ENDED), perfiles `ml` (bajo demanda).

## Rollback

```bash
cd /srv/apps/ia-bot-trading
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml stop
# o:
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml down   # SIN -v
```

## Seguridad

- PAPER_ONLY; sin keys de trading real
- Postgres no expuesto al host
- Mutaciones lab requieren `LAB_CONTROL_TOKEN`
- No reutilizar secretos de otros stacks del mismo servidor
