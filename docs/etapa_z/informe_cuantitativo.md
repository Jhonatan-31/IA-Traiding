# Etapa Z — Informe cuantitativo

## Datos

- Fuente: Binance Vision → Parquet OHLCV
- Símbolos: BTCUSDT, ETHUSDT, SOLUSDT
- Span: 2024-11-01 → 2025-10-31
- TF usados: **1d** (365 barras alineadas), **4h** (2190)
- Capital: 1000 USDT
- Costos: fee 10 bps + slip 5 bps + spread proxy 1 bp (half en one-way)
- Stress: neto − 0.5× fricciones acumuladas
- Splits: 70% IS / 20% OOS-Z / 10% holdout W **consumido** (no independiente)

## Configuración congelada

Ver `hypotheses.py` y `config_hash` en `etapa_z_results.json`.

## Resultados OOS (experimento Z-20261110T…)

| Hipótesis | Ops/rebal | P/L neto | DD | Exposición media | Costos | Stress | Validación |
|-----------|-----------|----------|----|-----------------|--------|--------|------------|
| Z-BH-BTC | 1 | −56.0 | 12.2% | 99% | 1.5 | −56.8 | benchmark |
| Z-BH-EQ | 167 | +201.8 | 13.0% | 98% | 3.0 | +200.3 | benchmark |
| Z-TSMOM-D28H5 | 136 | +340.5 | 13.0% | 95% | 23.0 | +329.0 | exploratoria |
| Z-TSMOM-VOL | 131 | +27.9 | 3.0% | 19% | 5.7 | +25.1 | descartada vs BH-EQ |
| Z-RS-TOP1 | 3 | +405.7 | 14.5% | 99% | 6.0 | +402.7 | descartada (muestra/N=3) |
| Z-4H-MOM12 | 506 | +103.3 | 16.5% | 66% | 210.2 | −1.7 | descartada (costos) |

## Metodología

- Señal en barra **cerrada**; rebalance al close con fricciones.
- Long-only spot; cash cuando señal ≤ 0.
- Sin short, sin apalancamiento.
- Comparación vs cash (0), BH-BTC y BH-EQ en el **mismo** intervalo.

## Limitaciones estadísticas

- N temporal corto (~73 días OOS diarios).
- Sin bootstrap reportado como decisión de promoción (muestra corta).
- Múltiples hipótesis preespecificadas (6); no grid masivo.
- Dependencia serial de retornos diarios cripto.

## Conclusión cuantitativa

Única línea exploratoria razonable: **TSMOM 28d long-only**. No validada fuera de muestra virgen.
