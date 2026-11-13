# AJ4 — Guía operativa de activación (EBZ, Tailscale 1.104.5)

**NO EJECUTAR** las fases B–D sin orden explícita del usuario.  
Esta guía está calibrada al estado real auditado el 2026-11-13.

CLI comprobada en EBZ: **Tailscale 1.104.5** · docs oficiales [tailscale serve](https://tailscale.com/kb/1242/tailscale-serve) (flags `--bg`, `--https=<port>`, `off`).

## Principios

- No usar `tailscale serve reset` (borra EVS/Consultate Serve).  
- No usar Funnel para Trading (`tailscale funnel` ≠ `serve`).  
- No tocar handlers existentes en 443 ni 8443.  
- Rollback por fase, sin `down -v`.  
- Certificados HTTPS de MagicDNS pueden figurar en CT logs (hostname ya expuesto por Funnel EVS).

---

## Fase A — Preflight (autorizado inspeccionar; ejecutar checks)

```bash
ssh consultate   # o Tailscale 100.107.168.61
cd /srv/apps/ia-bot-trading
grep -E '^(DASHBOARD_READ_AUTH|DEPLOY_GIT_COMMIT)=' .env
crontab -l | grep ebz_backup
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env ps
curl -sS http://127.0.0.1:8090/api/public/health
curl -sS http://127.0.0.1:8090/api/auth/status
tailscale serve status
tailscale funnel status
# Confirmar: Funnel solo EVS; 8443 Consultate; 10000 libre
ss -tlnp | grep -E ':8090|:10000'
ls -lah /srv/backups/ia-bot-trading | tail
```

Criterio GO: A/B STOPPED, health 200, auth OFF, Serve ajenos intactos, SSH OK.

---

## Fase B — HTTPS privado (REQUIERE AUTORIZACIÓN)

```bash
# Solo Trading en puerto dedicado — NO tocar 443/8443
sudo tailscale serve --bg --https=10000 http://127.0.0.1:8090
tailscale serve status
tailscale funnel status   # 10000 NO debe aparecer como Funnel
```

URL esperada (tailnet):

`https://servidor-ebz.tail528f82.ts.net:10000`

Pruebas:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://servidor-ebz.tail528f82.ts.net:10000/api/public/health
# Navegador: abrir UI, gráfico /ws/market
```

Rollback B:

```bash
sudo tailscale serve --https=10000 off
# Verificar que 443 Funnel EVS y 8443 Consultate siguen igual
tailscale serve status
tailscale funnel status
```

---

## Fase C — Autenticación (REQUIERE AUTORIZACIÓN)

```bash
cd /srv/apps/ia-bot-trading
# Generar token largo fuera de git, p.ej.:
# openssl rand -hex 32
# Editar .env (no commitear):
# DASHBOARD_READ_TOKEN=<valor>
# DASHBOARD_READ_AUTH=1
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env up -d api dashboard
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env restart dashboard
```

Pruebas:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://servidor-ebz.tail528f82.ts.net:10000/api/system
# → 401
# Login UI o:
curl -sS -c /tmp/jar -X POST https://…:10000/api/auth/login \
  -H 'content-type: application/json' -d '{"token":"<valor>"}'
curl -sS -b /tmp/jar -o /dev/null -w '%{http_code}\n' https://…:10000/api/system
# → 200
curl -sS http://127.0.0.1:8090/api/health   # healthcheck local sin auth
```

Rollback C:

```bash
# .env → DASHBOARD_READ_AUTH=0
docker compose -p ia-bot-trading -f deploy/ebz/docker-compose.yml --env-file .env up -d api dashboard
```

---

## Fase D — Restringir HTTP directo (REQUIERE AUTORIZACIÓN; solo tras B+C OK)

1. Cambiar publish a `127.0.0.1:8090:8080` en compose EBZ.  
2. Redeploy dashboard.  
3. Confirmar LAN `192.168.1.12:8090` ya no responde desde fuera del host.  
4. Confirmar HTTPS :10000 sigue OK.  
5. Confirmar Consultate/EVS intactos.

Rollback D: restaurar `0.0.0.0:8090:8080` + redeploy dashboard.

---

## Fase E — Postflight

- Auth 401/200 según sesión.  
- Mutaciones con `X-Lab-Token`.  
- AF reliability muestreando.  
- Cron backups intacto.  
- A/B STOPPED · PAPER_ONLY.  
- Funnel EVS y Serve Consultate sin cambios no autorizados.
