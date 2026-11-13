# AH0 — Inventario de rutas (post-AG / AH)

| Ruta | Método | Clase | Auth lectura ON | Mutación |
|------|--------|-------|-----------------|----------|
| `/api/public/health` | GET | PUBLIC | No | No |
| `/api/health` | GET | HEALTHCHECK | No | No |
| `/api/auth/status` | GET | AUTH BOOTSTRAP | No | No |
| `/api/auth/login` | POST | AUTH BOOTSTRAP | No (emite sesión) | No ledger |
| `/api/auth/logout` | POST | AUTH BOOTSTRAP | No | No |
| `/api/system` … `/api/positions` | GET | LECTURA SENSIBLE | Sí | No |
| `/api/demo|active|lab/*` POST | POST | CONTROL | Sí + `X-Lab-Token` | Sí |
| `/ws/market` | WS | PUBLIC MARKET | No* | No |
| Estáticos `/` | GET | UI SHELL | No (datos vía API) | No |

\* Fan-out Binance público; no transporta saldos/posiciones.

Producción actual: `DASHBOARD_READ_AUTH=0` → middleware no impone (compatibilidad).
