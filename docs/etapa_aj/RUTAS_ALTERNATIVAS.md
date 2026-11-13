# AJ2 — Cerrar rutas alternativas (diseño)

## Bypass actuales (con auth OFF)

| Vía | Riesgo | Mitigación futura (requiere autorización) |
|-----|--------|-------------------------------------------|
| `http://192.168.1.12:8090` | Lectura sensible LAN | Tras HTTPS+login OK: bind `127.0.0.1:8090` |
| `http://100.x:8090` | Lectura vía Tailscale IP HTTP | Idem bind loopback |
| API directa host | N/A (no publicada) | Mantener |
| Proxy headers falsos | Bajo en LAN | Confiar solo en Serve/local |
| `/ws/market` | Solo mercado público | Sin cambio |
| Funnel 443 EVS | Público (otro proyecto) | No mezclar Trading ahí |

## Orden seguro (no invertir)

1. Serve HTTPS :10000 verificado.  
2. Login `DASHBOARD_READ_AUTH=1` verificado.  
3. **Solo entonces** cambiar compose `0.0.0.0:8090` → `127.0.0.1:8090`.  
4. Conservar SSH + Tailscale como acceso de emergencia.

## Cambio mínimo propuesto (Fase D, autorización aparte)

En `deploy/ebz/docker-compose.yml`:

```yaml
ports:
  - "127.0.0.1:8090:8080"
```

No aplicar en AJ. No afecta Consultate/EVS.
