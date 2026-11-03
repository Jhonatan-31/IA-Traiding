# AI Trading Bot para Windows + Docker Desktop

Fase de laboratorio. **Sin claves, sin billetera y sin trading real.** Solo datos públicos de Binance, cruces SMA10/50 y simulación virtual, con PostgreSQL + FastAPI + dashboard HTML servido desde Nginx. No utiliza React en esta reconstrucción ligera del paquete: el dashboard es HTML/JS y se puede migrar a React en la siguiente iteración sin cambiar la API.

## Instalación en PowerShell

1. Copiar carpeta `ai_trading_bot_windows` a `C:\TradingBot`.
2. Abrir PowerShell y `cd C:\TradingBot\ai_trading_bot_windows`.
3. `Copy-Item .env.example .env`
4. `notepad .env` y cambiar `DB_PASSWORD` por cadena alfanumérica robusta sin caracteres especiales de URL.
5. `docker compose up -d --build`
6. `docker compose ps`
7. `docker compose logs --tail=50 worker`
8. Abrir `http://localhost:8088`.

## Limitaciones

- Simulación ilustrativa; no es backtest de ejecución, ni predicción IA ni promesa de ganancias.
- Cotizaciones sobre cierre de vela, slippage fijo y comisiones supuestas. No considera profundidad de libro ni liquidez a nivel de orden.
- Escanea hasta 25 pares con suficiente volumen; puede modificarse `SCAN_LIMIT` hasta 500.
- La base de datos persiste en volumen Docker. No usar `docker compose down -v` sin intención de borrarla.
- Dashboard solo accesible en localhost; evitar publicar sin autenticación.
- Antes de operar dinero real, verificar normas colombianas, restricciones de exchange, seguridad y pruebas cuantitativas.
