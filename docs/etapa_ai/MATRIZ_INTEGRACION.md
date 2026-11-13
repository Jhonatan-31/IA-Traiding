# AI0 — Matriz AF/AG/AH integración

| COMPONENTE | IMPLEMENTACIÓN | PRUEBA | ESTADO | RIESGO |
|------------|----------------|--------|--------|--------|
| SLI AF `/api/reliability` | samples/min | curl 200 · cov~0.96 | OPERATIVO | Bajo |
| `/api/public/health` | mínimo | curl 200 | OPERATIVO | Bajo |
| Auth lectura AG/AH | middleware+cookie | tests AI ON/OFF | PREPARADO_SIN_ACTIVAR | Lectura abierta mientras OFF |
| AuthGate UI | condicional | build OK | PREPARADO | — |
| Mutaciones | X-Lab-Token | AD/AH | OPERATIVO | Token en env |
| `/ws/market` | fan-out público | policy doc+código | OPERATIVO | No ledger |
| Cron backups | 00:00/12:00 Bogota | crontab sí; log no | PROGRAMADO | Primera corrida pendiente 2026-11-14 00:00 Bogota |
| HITACHI dumps | /srv/backups | sha256+restore 63 | VERIFICADO | Mismo host |
| Off-host | script | noop sin DEST | PREPARADO | Pérdida total host |
| Monitor externo | probe py | NOT_CONFIGURED | PREPARADO | Caída total invisible |
| A/B | STOPPED | SQL | OK | — |
