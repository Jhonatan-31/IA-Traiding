# AI3 — Migración segura de acceso (futura)

## Pasos verificables (no ejecutar ahora)

1. Confirmar SSH/Tailscale admin.  
2. Activar HTTPS privado (Serve) con autorización.  
3. Generar `DASHBOARD_READ_TOKEN` largo en `.env` (fuera de git).  
4. Probar en ventana de mantenimiento: `DASHBOARD_READ_AUTH=1` + recreate api/dashboard.  
5. Login desde PC y móvil autorizados.  
6. Verificar 401 sin sesión en `/api/system`.  
7. Verificar `/api/public/health` y Docker health sin cookie.  
8. Verificar `/ws/market` (público).  
9. Verificar mutaciones aún exigen `X-Lab-Token`.  
10. Si falla: `DASHBOARD_READ_AUTH=0` + recreate api (rollback sin perder AD–AH).

No contraseñas por defecto. No Secure sobre HTTP puro.
