# Etapa Y — Investigación causal de salidas

## Veredicto

**Hipótesis de salida no soportada.** Ninguna política Y1–Y4 mejora Y0 de forma robusta (neto, costos, exposición, expectativa positiva). Se descarta perseguir micro-ajustes de salida sobre las mismas entradas A / V-BREAK. El problema fundamental sigue siendo **falta de ventaja de entrada**.

- `exit_fix_hypothesis`: `not_supported_discard_minor_tweaks`
- `activate`: false · `declare_profitable`: false
- A y B permanecen **STOPPED** · PAPER_ONLY · sin cambios de carteras

## Seguridad

| Control | Estado |
|---------|--------|
| A | STOPPED |
| B | STOPPED |
| PAPER_ONLY | sí |
| PAPER_AI | deshabilitado |
| Lab / SMA | independientes |
| Checkpoint pre | `checkpoint-etapa-y-pre-20261110_150623` |
| Backup DB | `backups/paper_pre_etapa_y_20261110_150623.dump` |
| Base código | `checkpoint-etapa-x` / `237d015` |

## Método

1. Entradas fijas (mismas señales) para Y0–Y4 — comparación causal de salidas.
2. Señal en **1h cerrada**; trayectoria/SL-TP en **1m** verificada.
3. Intrabar ambiguo: **SL antes que TP**.
4. Invalidación de tendencia muestreada cada 5m; SL/TP cada 1m.
5. Walk-forward 70% IS / 20% OOS; holdout W **consumido**; post-oct-2025 **no disponible**.
6. Costos: fee+slip round-trip; estrés = neto OOS − 0.5×(fees+slips).

## Diagnóstico Y0 (OOS)

### Estrategia A

| Métrica | Valor |
|---------|-------|
| Ops | 486 |
| Neto | −38.50 USDT |
| Expectativa | −0.079 USDT/op |
| % MFE > costos | **24.9%** |
| % devolvió a pérdida | 14.0% |
| Captura media / MFE | −8.50 (descriptivo; no ejecutable) |
| Duración media | 27 min |
| MFE / MAE medios | 0.27% / 0.24% |
| Salidas | trend_break 473 · TP 11 · SL 2 |

Interpretación: la mayoría de operaciones **nunca supera costos** en MFE. Casi todas cierran por `trend_break` con movimiento favorable típico inferior al round-trip. No implica que “hubiera sido posible” capturar el MFE.

### V-BREAK

| Métrica | Valor |
|---------|-------|
| Ops | 155 |
| Neto | −10.16 USDT |
| Expectativa | −0.066 USDT/op |
| % MFE > costos | 71.6% |
| % devolvió a pérdida | **43.9%** |
| Duración media | 258 min |
| Salidas | sl_range 125 · tp_range 30 |

Interpretación: hay movimiento favorable post-entrada con más frecuencia, pero **casi la mitad** vuelve a pérdida neta; la salida original no convierte ese MFE en edge.

## Comparación Y0–Y4 (OOS, mismas entradas)

### A

| Política | Neto | Exp. | DD | Duración | Stress costos |
|----------|------|------|-----|----------|---------------|
| Y0 original | −38.5 | −0.079 | 3.9% | 27m | −56.7 |
| Y1 confirmación | −40.9 | −0.084 | 4.1% | 54m | −59.1 |
| Y2 trail ATR | −38.4 | −0.079 | 3.8% | 5m | −56.6 |
| Y3 tiempo 24h | −9.4 | −0.019 | 3.1% | 940m | −27.6 |
| Y4 SL/TP fijos | −28.5 | −0.059 | 3.0% | 759m | −46.7 |

Y3 reduce daño bruto pero **multiplica exposición (~35×)** y sigue con expectativa negativa → rechazada.

### V-BREAK

| Política | Neto | Exp. | Stress |
|----------|------|------|--------|
| Y0 | −10.2 | −0.066 | −16.0 |
| Y1 | −4.9 | −0.031 | −10.7 |
| Y2 | −11.5 | −0.074 | −17.3 |
| Y3 | −2.2 | −0.014 | −8.0 |
| Y4 | −10.6 | −0.068 | −16.4 |

Ninguna con expectativa positiva ni filtros de investigación aprobados.

## Candidatas

Todas **rejected** (filtros: no mejora neta / costos / exposición / expectativa ≤ 0).

## Limitaciones

- Orden intra-minuto desconocido (política SL-first).
- MFE ≠ ganancia capturable con certeza.
- Holdout W consumido; sin Parquet post-2025-10 para OOS temporal nuevo.
- Trend check cada 5m (no inventa orden dentro de la vela).
- Una mejora histórica aislada no autoriza operar.

## Entregables

1. Auditoría de trayectorias 1m — `exits_y.py` / `etapa_y_results.json`
2. Distribución MFE/MAE — `diagnosis_y0`
3. Diagnóstico entradas vs salidas — este informe + panel
4. Comparación Y0–Y4 — resultados OOS
5–8. Netos, DD, sensibilidad costos, regímenes por trade
9. OOS 20% (holdout W no reutilizado)
10. Limitaciones — arriba
11. Tests — `tests/test_etapa_y.py`
12. Carteras — sin cambios; A/B STOPPED
13. Commit / `checkpoint-etapa-y` / backup / rollback — `docs/etapa_y_rollback.md`

## Conclusión operativa

No activar estrategias. No seguir optimizando salidas menores sobre A/V-BREAK. Cualquier etapa siguiente debe abordar **nuevas entradas** o abandonar estas señales, no retocar stops/trailing sobre el mismo set.
