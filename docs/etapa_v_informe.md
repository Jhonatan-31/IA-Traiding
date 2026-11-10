# Etapa V — Informe de investigación cuantitativa

**Fecha:** 2026-11-10  
**Referencia previa:** Etapa U (`47195e7`)  
**Modo:** PAPER_ONLY · A STOPPED · B STOPPED · PAPER_AI off  
**Checkpoint pre:** `checkpoint-etapa-v-pre-20261110_113700` · backup `backups/paper_pre_etapa_v_20261110_113700.dump`

Esta etapa es de **investigación**, no de despliegue. Ninguna estrategia nueva se activó.

---

## 1. Auditoría exacta de A (forense)

Reconstrucción FIFO desde el libro de operaciones Demo. Slippage **no** se resta dos veces (ya está en el precio de fill).

| Métrica | Valor verificado |
|---|---|
| Efectivo en cuenta | 990,805739 USDT |
| Efectivo reconstruido | 990,805739 USDT |
| Discrepancia cash | **0,00** |
| Rondas cerradas | 56 |
| P/L realizado (neto motor) | −7,801771 USDT |
| Comisiones (atribución) | 2,778558 USDT |
| Slippage (atribución) | 1,389283 USDT |
| Coincide reporte Etapa U | sí |

**P/L neto por motivo de salida**

| Motivo | P/L neto |
|---|---|
| Tendencia debilitada (`trend_break_1m`) | −6,110988 |
| Stop-loss 1% | −4,105063 |
| Take-profit 2% | +2,414280 |

**Diagnóstico de fuentes de pérdida (hechos, no hipótesis):**

1. **Salidas por invalidación de tendencia** concentran la mayor pérdida neta.
2. **Stops** aportan pérdida adicional; el TP no compensa el conjunto (PF histórico ~0,25 en auditoría económica previa).
3. **Costos** (fee+slip) erosionan el edge aparente; ya están reflejados en fills/P&L — no deben restarse otra vez al patrimonio.
4. Win rate bajo (~12,5% en reporte U) + expectancy negativa ≈ −0,14 USDT/op.

**Limitaciones forenses:** MFE/MAE intrabar y régimen por operación no están persistidos en el libro Demo; requieren enriquecimiento offline con klines entre entrada/salida.

---

## 2. Investigación externa

Ver `docs/etapa_v_investigacion_externa.md` (DOI/URL, metodología, limitaciones). Insumos, no promesas de rentabilidad.

---

## 3. Calidad de datos históricos (corte V)

| Aspecto | Estado |
|---|---|
| Símbolos | BTCUSDT, ETHUSDT, SOLUSDT |
| Fuente backtest V | API pública 1m (~999 barras ≈ 16,6 h) |
| Meta 12–24 meses | **Pendiente** de ingesta histórica persistida |
| Walk-forward | 70% IS / 30% OOS (split índice 699 / 999) |
| Look-ahead | Señales solo con velas cerradas; fill en close±slip |
| Huecos/duplicados | Ventana corta de API; sin auditoría multi-mes en este corte |

No se comparan periodos operativos distintos como si fueran equivalentes.

---

## 4. Diagnóstico por régimen (simulador V)

Clasificador determinista (EMA tendencia + ATR vol) usando solo historia disponible hasta la barra de decisión (`look_ahead_safe`).

En OOS de esta ventana corta, el baseline A concentró pérdidas en `sideways|low_volatility` (21 rondas, suma −3,145). Eso **sugiere** dificultad en lateral, pero la muestra es demasiado corta para generalizar.

V-TREND / V-BREAK no generaron fills OOS en esta ventana (filtros estrictos + datos insuficientes para HTF 1h estable).

---

## 5. Reglas versionadas

Congeladas en `backend/app/research/policies_v.py` **antes** de mirar OOS:

- **V-TREND** `v_trend_pullback_v20261110`
- **V-BREAK** `v_breakout_v20261110`
- **V-MEAN** `v_mean_revert_v20261110` (secundaria; sin martingala; max_adds=0)
- **V-IA** solo observación; `execution_authorized=false`

A y B baselines inmutables.

---

## 6–9. Backtest realista, OOS, costos, sensibilidad

Costos modelo: fee taker 10 bps · slip 5 bps · tamaño máx 25 USDT · máx 3 posiciones · exposición 75 USDT.

### Resultados OOS (misma ventana ~16,6 h)

| Estrategia | Neto vs 1000 | Rondas | Win rate | PF | Fees | Slip | DD proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| A_BASELINE | −3,145 | 21 | 0% | 0 | 1,047 | 0,524 | 0,31% |
| V_TREND | 0,000 | 0 | — | — | 0 | 0 | 0 |
| V_BREAK | 0,000 | 0 | — | — | 0 | 0 | 0 |
| V_MEAN | +0,010 | 4 | 50% | 1,02 | 0,200 | 0,100 | 0,06% |
| Efectivo | 0 | 0 | — | — | 0 | 0 | 0 |
| B (ventana completa, descriptivo) | −0,448 | — | — | — | 0,100 | — | — |

**Gate de aprobación:** V_TREND / V_BREAK / V_MEAN → **rechazadas** (pocas operaciones OOS y/o neto no positivo).  
`promote_to_paper_trial=false` siempre sin autorización explícita.

Sensibilidad / Deflated Sharpe: no interpretables con N tan bajo; documentado como limitación. No se optimizó sobre el OOS.

---

## 10. Predicciones IA

- 264 predicciones resueltas auditadas.
- Sin probabilidad calibrada persistida (0 con calibración).
- Retorno observado medio reportado ≈ +0,42 pp — **no** constituye edge operable (dependencia, selección, costos, independencia).
- PAPER_AI off · sin ejecución automática.

---

## 11. Tabla comparativa de candidatos

Ver sección 6 y dashboard `/investigacion`. Estado UI: En investigación / Rechazada / Baseline / Solo observación. **Ninguna candidata a prueba prospectiva** en este corte.

---

## 12. Conclusión

1. A pierde por combinación de **salidas (trend_break + SL)** y **costos**, no por falta de frecuencia de compra.
2. En la ventana corta disponible, **ninguna** hipótesis V cumple filtros de investigación para prueba autónoma.
3. Hace falta **historia 12–24 m** antes de reinterpretar V-TREND/V-BREAK.
4. No se declara rentabilidad ni se activa estrategia nueva.

---

## 13. Pruebas automatizadas

`pytest tests/test_etapa_v.py tests/test_etapa_u_research.py` → **6 passed**.

---

## 14. Capturas

`docs/screenshots/etapa_v_centro_investigacion.png`

---

## 15. Docker y carteras

- A `bot_status=STOPPED`
- B `bot_status=STOPPED`
- PAPER_ONLY vigente
- Servicios Compose activos; dashboard `:8088`

---

## 16. Commit / checkpoint / rollback

- Tag pre: `checkpoint-etapa-v-pre-20261110_113700`
- Backup: `backups/paper_pre_etapa_v_20261110_113700.dump`
- Rollback código: `git checkout checkpoint-etapa-v-pre-20261110_113700` (o tag post `checkpoint-etapa-v`)
- Rollback datos: restaurar dump Postgres (ver `docs/etapa_v_rollback.md`)
