# AI Trading Bot Pro (PAPER ONLY)

Laboratorio de simulación sobre Binance Spot **público**. Sin claves privadas, sin billetera y sin órdenes reales. No promete ganancias.

## Ruta del proyecto (verificada)

`C:\Users\JHONATAN RINCON\OneDrive\Escritorio\MESA DE TRABAJO\IA BOT TRAIDING`

La ruta `C:\TradingBot\ai_trading_bot_windows` **no existe** en este entorno.

## Stack

- Docker Desktop + WSL 2
- PostgreSQL 16 (`iabottraiding_paper_data`)
- FastAPI + worker paper trading (SMA10/SMA50 1h)
- Dashboard React + TypeScript + Vite (Nginx)

## Arranque (PowerShell)

```powershell
cd "C:\Users\JHONATAN RINCON\OneDrive\Escritorio\MESA DE TRABAJO\IA BOT TRAIDING"
Copy-Item .env.example .env   # solo si no existe
# Editar DB_PASSWORD (alfanumérico, sin caracteres especiales de URL)
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 worker
```

Abrir: http://localhost:8088

## Comandos útiles

```powershell
docker compose logs -f api worker dashboard
docker stats --no-stream
docker compose exec -T db psql -U paper -d paper -c "SELECT * FROM account;"
# Backup (antes de migraciones)
docker compose exec -T db pg_dump -U paper -d paper --no-owner --no-acl > backups\paper_backup.sql
```

## Rollback seguro

- **No** ejecutar `docker compose down -v` (borra el volumen).
- Revertir código: `git checkout -- .` o volver a un commit previo.
- Restaurar SQL: `Get-Content backups\archivo.sql | docker compose exec -T db psql -U paper -d paper`
- Tras recrear `api`, si hay 502: `docker compose restart dashboard`

## API principal

| Método | Ruta | Uso |
|--------|------|-----|
| GET | `/api/health` | Health real (incluye DB) |
| GET | `/api/overview` | Resumen cartera |
| GET | `/api/positions` | Posiciones + P/L no realizado |
| GET | `/api/trades` | Historial |
| GET | `/api/scans` | Equity por ciclo |
| GET | `/api/markets` | Precios cacheados |
| GET | `/api/system` | Observabilidad básica |
| GET | `/api/diagnostics/binance` | Ping público Binance |
| POST | `/api/engine/pause` | Pausar simulación |
| POST | `/api/engine/resume` | Reanudar |

## Limitaciones actuales

- Gráficas OHLCV, IA entrenada, backtesting completo y alertas externas: pendientes.
- Métricas ausentes se muestran como **Sin datos** (no se inventan).
- Otros contenedores Docker del host no pertenecen a este proyecto y no deben tocarse.
