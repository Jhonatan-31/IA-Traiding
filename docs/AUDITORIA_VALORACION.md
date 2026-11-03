# Auditoría de valoración y resolución Shadow

**UTC:** 2026-11-03T22:27–22:35Z · **Base:** `365a801` · PAPER_ONLY · sin cambio de estrategia.

## 1. Causa del drawdown ≈0,002%

**No era un redondeo del −0,043% vs capital inicial.**

| Concepto | Valor observado |
|----------|-----------------|
| Capital inicial | 1000 |
| Patrimonio MTM | ≈999,54–999,57 |
| `return_vs_initial` | ≈ **−0,043%** = (equity−1000)/1000 |
| Peak buggy | ≈999,58 |
| `drawdown_vs_peak` buggy | ≈ **0,002%** = (999,58−equity)/999,58 |

**Fórmula buggy** en `valuation.py`:

```sql
MAX(COALESCE(end_equity, start_equity))
```

Con `start_equity=1000` y `end_equity≈999.58`, `COALESCE` elige el fin del día y **descarta el pico 1000**.

**Fórmula correcta:** `peak = max(initial, start_equity, end_equity)` →  
`drawdown = (peak − equity) / peak` ≈ **0,043%**.

Unidades: fracción (0,00043) ≡ 0,043%. El dashboard mostraba la fracción con 4 decimales → aparente “casi cero”.

Motor de riesgo lab usa peak en tiempo real distinto; el DD del dashboard venía solo de `lab_equity_daily`.

## 2. Corrección justificada

- `peak_equity_from_daily_rows` + `drawdown_fraction` en `reconcile_valuation.py`.
- API expone `drawdown_vs_peak_pct`, `peak_basis`, `equity_daily`, `reconciliation`.
- UI etiqueta “DD vs peak” con % y peak.

Verificado post-fix: `peak=1000`, `dd_pct≈0.046%` (coherente con retorno vs inicial).

## 3. Reconciliación laboratorio (identidad OK)

`equity_gross = cash + Σ(qty×mark)` coincide con API.

| Ítem | ≈ |
|------|---|
| Efectivo | 924,87 |
| Coste posiciones | 75,00 |
| MV posiciones | ≈74,7 |
| uPnL | ≈−0,30 |
| P/L realizado | −0,1346 |
| Fees acum. | ≈0,125 |
| Patrimonio bruto | ≈999,54 |
| Patrimonio neto est. (tras fee/slip teóricos de salida) | bruto − costes salida estimados |

Pruebas: `tests/test_valuation_reconcile.py`.

## 4. Shadow

| Lote (vela open) | Resoluble después | ¿Listo ahora? |
|------------------|-------------------|---------------|
| 2026-11-03 **18:00** UTC (ids 1–5) | **2026-11-04 01:00** UTC | No |
| 2026-11-03 **19:00** UTC (ids 6–10) | **2026-11-04 02:00** UTC | No |
| 20:00 → 03:00; 21:00 → 04:00 | | No |

20 PENDING; **0 resueltas anticipadamente**. Scheduler autónomo OK (`resolved: 0` hasta horizonte).

## 5. Scheduler / seguridad / carteras

- trade-executor + shadow-scheduler Up; PAPER_ONLY; PAPER_AI off; sin órdenes reales.
- SMA paper: cash 825 / 7 pos / integridad OK.
- research_sim: 1000.
- lab_auto: cash ≈924,87 / 3 pos.

## 6. Errores

1. **Peak COALESCE** (corregido).
2. Presentación DD sin unidad/% (mejorada en UI).
3. Ningún error de resolución Shadow prematura.
