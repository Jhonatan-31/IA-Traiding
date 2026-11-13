# Etapa AA — Auditoría adversarial

| # | Pregunta | Severidad | Hallazgo |
|---|---|---|---|
| 1 | ¿Gana solo porque el mercado subió? | Media | Mercado bajó; D28H5 también pierde en absoluto (−126). Ventaja = menor pérdida. |
| 2 | ¿Solo porque ETH/SOL > BTC? | Baja | BH-EQ (−398) peor que BTC (−296); alts no “salvaron” el período. |
| 3 | ¿Desaparece con costos altos? | Alta | `cost_stress_net` D28H5 = −163; neto absoluto ya negativo. |
| 4 | ¿Concentración en pocas ops? | Baja | 356 turnovers; top5 días = 20,8% del exceso positivo. |
| 5 | ¿Un mes extraordinario? | Media | Mejor mes 2026-08 (+15,9%); BH-EQ ese mes +34% — no explica sola la ventaja relativa. |
| 6 | ¿Look-ahead? | — | Comprobado en sintéticos + contrato Z; freeze OK. |
| 7 | ¿Precios inejecutables? | Media | Close + fee/slip/spread proxy; sin BBO. |
| 8 | ¿Benchmark con costos distintos? | — | Mismo motor de fricciones. |
| 9 | ¿Más exposición? | — | D28H5 **menos** exposición (55% vs 99%). |
| 10 | ¿Ajuste post-hoc? | — | No; hash congelado. |
| 11 | ¿Tratamiento temporal distinto? | — | UTC 1d idéntico. |
| 12 | ¿DD omite intraperíodo? | Media | DD sobre close diario; riesgo intradía no medido. |

**Críticos de bloqueo:** 0. **Promoción:** bloqueada por reglas AA10 (stress, IC, P/L absoluto).
