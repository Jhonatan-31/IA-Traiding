# Auditoría económica de operaciones — Estrategia A (Conservadora)

**Fecha:** 2026-11-10 (~15:20 UTC)  
**Modo:** PAPER_ONLY · sin cambio de reglas · B no iniciada · IA sin ejecución  
**API:** `GET /api/active/economic`  
**UI:** Inicio → sección «¿Cómo le está yendo a mi bot?»

## Conclusión en una frase

La mayor frecuencia de A **no está generando valor neto**: el patrimonio virtual pasó de **1.000 → ≈991,42 USDT** (Δ **−8,58**), con **win rate 13,2%** sobre 53 operaciones cerradas.

## Reconciliación

| Concepto | Valor |
|---|---:|
| Capital inicial | 1.000,00 |
| Efectivo (cash) | ≈941,82 |
| Costo posiciones abiertas | ≈49,60 |
| Patrimonio reconciliado (cash + MTM/costo) | ≈991,42 |
| Peak equity | ≈1.002,55 |
| Drawdown vs peak | ≈1,11% |
| Órdenes FILLED BUY/SELL | 55 / 53 |
| Trades BUY/SELL | 55 / 53 |
| Match órdenes↔trades | **sí** |
| Rondas FIFO cerradas | 53 |
| Posiciones abiertas | 2 (no cuentan como ganadoras) |

## Operaciones cerradas

| Métrica | Valor |
|---|---:|
| Ganadoras / perdedoras | 7 / 46 |
| Win rate | 13,21% |
| Ganancia media | +0,37 USDT |
| Pérdida media | −0,21 USDT |
| Profit factor | 0,26 |
| Expectativa neta / operación | −0,14 USDT |
| P/L realizado | −7,21 USDT |
| Comisiones totales | 2,68 USDT |
| Slippage registrado | 1,34 USDT |
| Duración media | ≈6,6 h (inflada por holds largos 5→10 nov) |

## Por qué bajó de 1.000 a ≈991

| Fuente | Impacto (USDT) | Lectura |
|---|---:|---|
| Salidas por tendencia debilitada | **−5,52** (44 ops, 42 pérdidas) | Principal lastre: muchas salidas pequeñas en rojo |
| Stop-loss (−1%) | **−4,11** (4 ops) | Golpe fuerte el 10/11 (BTC/ETH/SOL) |
| Take-profit (+2%) | **+2,41** (5 ops) | Únicas ganancias consistentes; no compensan |
| Comisiones | −2,68 | Coste de operar con frecuencia |
| Slippage | −1,34 | Ya en precio de fill; se reporta para atribución |
| No realizado (abiertas) | ≈0 en este snapshot* | Compras abiertas ≠ ganadoras |

\*Si el mark en vivo no responde, el no realizado usa precio de entrada (proxy). El patrimonio ≈ cash + costo abierto sigue reconciliando el deterioro de efectivo + posiciones.

**Lectura:** operar más a menudo en A está **quemando edge** vía micro-pérdidas por `trend_break_1m` + stops, no por falta de ciclos.

## Por criptomoneda (cerradas)

| Mercado | Cerradas | Wins | Losses | P/L |
|---|---:|---:|---:|---:|
| ETH | 24 | 3 | 21 | −3,48 |
| SOL | 15 | 3 | 12 | −2,36 |
| BTC | 14 | 1 | 13 | −1,38 |

## Frente a mantener efectivo

Mantener 1.000 USDT en caja = 0 variación.  
El bot ≈ **991,42** → **peor que cash** en ≈8,58 USDT hasta este corte.

## Comparación A/B (preparada, B detenida)

- B: **STOPPED**, cash 1.000, 0 trades, sin auto-inicio.
- Ancla prospectiva lista en `/api/active/economic` → `ab_prospective.prospective_anchor`.
- Regla: comparar solo el periodo en que **ambas** estén RUNNING por decisión del usuario.
- `declare_winner: false`.

## Pruebas

```text
pytest tests/test_economic_audit.py tests/test_active_diagnose_t1.py tests/test_active_policy_b.py
→ 12 passed
```

## Docker

Servicios Up: api, dashboard (:8088), db healthy, demo-runner, active-runner, market-stream, worker, trade-executor, shadow-scheduler.

## Datos faltantes / matices

1. Serie histórica continua de equity Demo (curva día a día) sigue limitada en Inicio.
2. Unrealized MTM depende de klines públicas; si fallan, se usa entrada como proxy.
3. El `realized_pnl` del motor ya incluye el efecto del slip en el precio de fill; fees se suman aparte para atribución (no restar dos veces al interpretar).
4. No se retocaron umbrales ni se reiniciaron saldos.
