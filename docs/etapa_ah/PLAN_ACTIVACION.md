# AH9 — Plan de activación gradual (NO ejecutar ahora)

## Preflight

1. Backup HITACHI reciente + sha256 OK.  
2. A/B STOPPED · PAPER_ONLY.  
3. API/dashboard/market-stream healthy.  
4. `DASHBOARD_READ_TOKEN` largo en `.env` EBZ (no en git).  
5. Acceso SSH/Tailscale alternativo verificado.  
6. Preferible: HTTPS privado (Tailscale Serve) autorizado.  
7. Suite AH/AG/AF en verde.  
8. Rollback documentado (abajo).

## Prueba limitada (aislado)

```bash
# En contenedor/api de prueba o temporal:
DASHBOARD_READ_AUTH=1 DASHBOARD_READ_TOKEN='…' uvicorn …
curl -i http://127.0.0.1:8000/api/system   # → 401
curl -i -H "X-Dashboard-Read-Token: …" http://127.0.0.1:8000/api/system  # → 200
curl -i -c jar -X POST http://127.0.0.1:8000/api/auth/login -H 'content-type: application/json' -d '{"token":"…"}'
curl -i -b jar http://127.0.0.1:8000/api/system  # → 200
```

No usar ledgers operativos para mutaciones de prueba.

## Activación producción (solo con autorización explícita)

1. Preflight OK.  
2. Añadir a `.env`: `DASHBOARD_READ_AUTH=1` y `DASHBOARD_READ_TOKEN=…`.  
3. `scripts/deploy_trading_ebz.ps1` (o recreate api/dashboard).  
4. Verificar login UI + denegación sin sesión.  
5. Verificar `/api/public/health` y Docker healthchecks sin token.  
6. Verificar `/ws/market` (fan-out público) sigue vivo.  
7. Verificar A/B STOPPED e integridad.

## Postflight

- Lecturas 401 sin sesión.  
- Lecturas 200 con sesión.  
- Mutaciones siguen exigiendo `X-Lab-Token`.  
- Cron AG intacto.  
- Consultate/EVS intactos.

## Rollback (sin perder AD–AG)

1. En `.env`: `DASHBOARD_READ_AUTH=0` (quitar o comentar).  
2. Redeploy/recreate **solo** api (y dashboard si hace falta).  
3. **No** `down -v`, **no** prune, **no** revertir a tags pre-AD.  
4. Confirmar `/api/system` 200 sin cookie y bots STOPPED.

## Estado AH

**NO ejecutar** activación en producción en esta etapa.
