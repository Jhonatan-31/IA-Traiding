# Etapa Q — Validación prospectiva y panel de rendimiento

Evidencia tomada ~**2026-11-04 00:05 UTC** · PAPER_ONLY · sin forzar resoluciones.

## 1. Estado Shadow LIVE

| Métrica | Valor |
|---------|-------|
| PENDING | **30** (6 lotes × 5 símbolos; crece con cada vela 1h) |
| RESOLVED | **0** |
| INVALID | 0 |
| `ready_now` @ 00:05 UTC | **0** |
| Primer horizonte completo | **2026-11-04 01:00 UTC** |
| Lotes listos (5 símbolos c/u) | 01:00, 02:00, 03:00, 04:00, 05:00, (+06:00 si hay lote 23:00) |
| `sample_sufficient` (≥30 resueltas) | **false** |

**Declaración explícita:** aún **no hay predicciones efectivamente resueltas**. No se adelantan outcomes. El scheduler resolverá solo cuando existan las 6+1 velas 1h.

Evaluación predictiva (`prospect_outcomes` / `/api/prospect/report`) ≠ rentabilidad de cartera ejecutable (`lab_auto` / SMA paper). HOLD no es trade; BUY Shadow no muta ledgers.

## 2. Predicciones resueltas

Ninguna. Campos solicitados (precio final, retorno, resultado, calidad) **N/A hasta RESOLVED**.

## 3. Resultado neto por cartera (API `/api/performance/compare`)

| Ledger | Inicial | Cash | Equity MTM | Retorno neto | rPnL | uPnL | Fees | Slip |
|--------|---------|------|------------|--------------|------|------|------|------|
| SMA paper | 1000 | 775 | 998.86 | −0.1138% | 0 | −1.14 | ~0.225 | (en fees est.) |
| Lab auto | 1000 | 924.87 | ~999.28 | ~−0.072% | −0.135 | ~−0.62 | 0.125 | 0.125 |
| research_sim | 1000 | 1000 | 1000 | 0% | — | — | 0 | 0 |

## 4. Operaciones virtuales cerradas

| Id | Symbol | Side | rPnL | Reason | ¿Demo/verif? |
|----|--------|------|------|--------|--------------|
| 2 | BTCUSDT | SELL | −0.1346 | `demo_verification_sell` | **Sí** |

Posiciones Lab abiertas (orgánicas): BTC, SOL, ZEC (coste 25 c/u). **No contar el SELL de verificación como performance de estrategia.**

## 5. Drawdown y costos

- SMA max DD: **−0.0809%** (peak 999.67, 12 puntos `scans`)
- Lab DD vs peak: **~0.00076** (fracción)
- Lab fees+slip acumulados ≈ **0.25** (fee 0.125 + slip 0.125 en trades)

## 6. Períodos sin cobertura (suspensión)

| Fuente | Gap | ~Ciclos omitidos | Ventana |
|--------|-----|------------------|---------|
| Windows Event Viewer | sleep→wake | — | **22:51:26Z → 23:31:14Z** (Power Button) |
| `shadow_scheduler_cycles` | 2678 s | ~8 | post ciclo #35 → #36 |
| `lab_cycles` | 2678 s | ~8 | post ciclo #33 → #34 |

Política: **no se reconstruyen** precios/salidas/trades durante el hueco.

## 7. Integridad ledgers

`ledgers_separated=true` · `paper_only=true` · `shadow_executing=false` · `paper_ai_disabled=true`  
Volúmenes/contenedores ajenos intactos.

## 8. Pruebas

- SQL: pending/ready_now, gaps, trades, equity
- API compare: curvas, downtime, closed_sells flag
- Dashboard `/performance` HTTP 200; datos alineados con PG (cash 775 / 924.87 / 1000)

## 9. Capturas

- `docs/screenshots/etapa-q-performance-top.png`
- `docs/screenshots/etapa-q-performance-coverage.png`

## 10. Pendientes

1. Esperar ≥01:00 UTC 4-nov para primeras resoluciones automáticas.
2. No optimizar estrategia con n≪30 resueltas.
3. Separar en reportes futuros el `demo_verification_sell` del PnL orgánico.
4. Más puntos en `lab_equity_daily` (hoy 1 día) para curva Lab más densa.

## Seguridad (cumplido)

PAPER_ONLY · sin órdenes reales · sin cambio de umbrales/balances · sin borrar volúmenes · sin tocar otros proyectos Docker.
