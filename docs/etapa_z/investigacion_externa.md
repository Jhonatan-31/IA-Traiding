# Etapa Z1 — Investigación externa documentada

Separación: **hallazgo publicado** vs **inferencia nuestra**.

## Fuentes primarias / académicas

### 1. Moskowitz, Ooi, Pedersen (2012) — Time Series Momentum
- **Enlace:** https://www.sciencedirect.com/science/article/pii/S0304405X11002613
- **Mercado:** futuros equity/FX/commodity/bonos (58 instrumentos)
- **Frecuencia:** mensual
- **Método:** signo del retorno pasado 1–12m; sizing por volatilidad
- **Costos:** literatura clásica (futuros líquidos)
- **Resultado:** persistencia 1–12m con reversión parcial a más largo plazo
- **Limitaciones:** no es spot cripto retail
- **Reproducible con nuestros datos:** parcialmente (spot long-only, 3 activos, 12m)

### 2. Han / Kang / Ryu — TS & CS momentum cripto bajo supuestos realistas
- **Enlace:** https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf
- **Mercado:** cripto (Binance futures para short); muestra amplia 2013–2023
- **Costos:** ~15 bps/trade; tick; slippage empírico; riesgo de liquidación
- **Resultado:** TSMOM más fuerte que CSMOM; muchos portfolios “significativos” no son rentables tras costos/liquidación
- **Limitaciones:** futures + short; no idéntico a nuestro spot long-only
- **Inferencia nuestra:** justificar prueba de TSMOM diario con costos conservadores; no esperar CSMOM robusto en N=3

### 3. Bitcoin intraday TSMOM (FIRE)
- **DOI:** https://doi.org/10.1111/fire.12290
- **Hallazgo:** momentum intradía ligado a volumen/volatilidad
- **Inferencia nuestra:** Etapa Y ya descartó micro-ajustes de salida intradía sobre A; no repetir sin datos nuevos de flujo

### 4. Liu & Tsyvinski / factores cripto
- Momentum a horizontes de semanas aparece en literatura de factores cripto
- **Inferencia nuestra:** horizontes 4h–días son el candidato natural post-Y

### 5. Binance Public Data / Vision
- **Enlace:** https://github.com/binance/binance-public-data · https://data.binance.vision/
- **Funding:** `futures/um/monthly/fundingRate`
- **Métricas OI:** `futures/um/daily/metrics` (archivos diarios; estimar tamaño antes de bajar 12m)
- **REST OI hist:** solo ~1 mes reciente
- **Klines:** incluyen taker_buy_* — **no persistidos** en nuestro Parquet actual

## Afirmaciones comerciales de bots
**No usadas** como evidencia científica de rentabilidad.

## Conclusión Z1
La literatura apoya **probar** TSMOM de medio plazo con costos realistas; no garantiza edge en BTC/ETH/SOL spot 2024-11→2025-10. CSMOM en universo de 3 es débil a priori.
