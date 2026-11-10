# Etapa V — Investigación externa (fuentes y lectura crítica)

**Fecha de consulta:** 2026-11-10  
**Uso:** insumos metodológicos. **No** constituyen garantía de rentabilidad.

| # | Fuente | Enlace | Lectura aplicable |
|---|---|---|---|
| 1 | Momentum y gestión de riesgo en crypto | https://www.sciencedirect.com/science/article/pii/S1544612325011377 | Motiva filtros de riesgo y que el momentum no es estable sin controles |
| 2 | Dependencia del momentum del régimen | https://doi.org/10.1016/j.frl.2025.108356 | Apoya diagnóstico por régimen (tendencia vs lateral) |
| 3 | Costos y anomalías crypto | https://doi.org/10.1016/j.irfa.2024.103218 | Costos pueden eliminar edges aparentes — alineado con fee+slip en A |
| 4 | Deflated Sharpe / sobreajuste | https://doi.org/10.2139/ssrn.2460551 | Penalizar selección entre muchas variantes; no crownear IS |
| 5 | Freqtrade strategy customization | https://www.freqtrade.io/en/stable/strategy-customization/ | Decisiones en velas cerradas, callbacks, evitar look-ahead |
| 6 | Tarifas Binance Spot | https://www.binance.com/en/fee/trading | Referencia taker ~0.1% retail (verificar cuenta VIP); usamos 10 bps en paper |
| 7 | Filtros Binance Spot | https://github.com/binance/binance-spot-api-docs/blob/master/filters.md | LOT_SIZE / NOTIONAL / PRICE_FILTER en ejecución realista |

## Metodología adoptada en el simulador V

- Señal solo con velas **cerradas**.
- Fill en `close * (1±slip)`; fee taker 10 bps.
- Walk-forward 70% IS / 30% OOS; **no** optimizar con el OOS.
- Hipótesis **congeladas** en `policies_v.py` antes de mirar OOS.
- A/B baselines inmutables.
- Meta de datos 12–24 meses: **pendiente** de ingesta histórica persistida; el corte actual usa ~1000 velas 1m de API pública (limitación explícita).

## Limitaciones

Paywalls académicos pueden restringir el texto completo; se citan DOI/URL. Resultados de papers no se trasladan 1:1 a BTC/ETH/SOL spot paper del bot.
