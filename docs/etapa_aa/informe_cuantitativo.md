# Etapa AA — Informe cuantitativo

Capital inicial: **1.000 USDT**. Período: **2025-11-01 → 2026-10-31** (365 barras 1d). Experimento: `AA-20261113T150418Z`.

## Tabla principal

| Estrategia | Final | P/L neto | Exceso vs BH-EQ | DD máx | Exp. media | Costos | Turnovers | Cash days | Sharpe proxy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Z-TSMOM-D28H5 | 873,58 | −126,42 | **+271,90** | 29,56% | 55,5% | 72,73 | 356 | 153 | −0,26 |
| Z-BH-EQ (primario) | 601,68 | −398,32 | 0 | 57,74% | 99,6% | 3,29 | 470 | 1 | −0,68 |
| Z-BH-BTC | 703,57 | −296,43 | +101,90* | 46,97% | 99,7% | 1,55 | 1 | 1 | −0,58 |
| CASH | 1.000 | 0 | +398,32* | 0% | 0% | 0 | 0 | — | — |

\*Exceso de D28H5 vs esa referencia no es la métrica primaria.

## Métrica primaria (prerregistrada)

Exceso neto D28H5 − BH-EQ = **+271,9002 USDT**.

## Stress de costos

| | cost_stress_net |
|---|---:|
| D28H5 | −162,79 |
| BH-EQ | −399,97 |

## Peores episodios (D28H5)

- Peor día: −6,03%
- Peor semana (~7d): −11,82%

## Retornos mensuales D28H5

| Mes | Ret |
|---|---:|
| 2025-11 | 0,0% |
| 2025-12 | −5,1% |
| 2026-01 | −11,7% |
| 2026-02 | 0,0% |
| 2026-03 | −9,3% |
| 2026-04 | +1,8% |
| 2026-05 | −8,0% |
| 2026-06 | 0,0% |
| 2026-07 | +1,4% |
| 2026-08 | +15,9% |
| 2026-09 | +12,4% |
| 2026-10 | −8,3% |

## Estadística

- Bootstrap bloques (block=5, n=400) media exceso diario: 0,000767
- IC95: [−0,001605, 0,003033] — **incluye cero**
- Top-5 días positivos / suma positivos: 20,8% (no concentración extrema)

## Contabilidad de operaciones

Turnover_events = ajustes de notional ≥1 USDT, **no** round-trips cerrados. Reconciliación Z OOS: 136 turnovers / neto +340,5377 (exacto).

## Independencia

`evaluacion_temporal_nueva_previa_no_utilizada` (pre-ingesta AA). Evaluación **consumida**.
