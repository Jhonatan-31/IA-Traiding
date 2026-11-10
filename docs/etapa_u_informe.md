# Etapa U — Investigación de pérdidas y mejora inteligente

**Checkpoint pre:** `checkpoint-etapa-u-pre-20261110_103023`  
**Backup:** `backups/paper_pre_etapa_u_20261110_103023.dump`  
**Pausa A:** 2026-11-10T15:25:49.237318Z (conservada)  
**PAPER_ONLY · A STOPPED · B STOPPED · PAPER_AI off**

## 1. Patrimonio actualizado de A

| Concepto | Valor |
|---|---:|
| Capital inicial | 1.000,00 |
| Efectivo (cash) | **990,81** |
| Posiciones abiertas | **0** |
| Valor de mercado abierto | 0 |
| **Patrimonio** | **990,81** |
| P/L realizado | −7,80 |
| P/L no realizado | 0 |
| Comisiones totales | 2,78 |
| Slippage registrado | 1,39 |
| Peak equity | 1.002,55 |
| Drawdown vs peak | ≈1,17% |
| Retorno total vs inicial | **−0,92%** (Δ −9,19) |

**No confundir cash con patrimonio:** hoy coinciden porque no hay inventario abierto.

### Reconciliación vs auditoría ~991,42

Entre ambas lecturas el bot (aún RUNNING, luego STOPPED con protecciones) cerró más rondas:

- Compras/ventas: 55/53 → **56/56**
- BTC abierto se vendió en STOPPED por `trend_break_1m` (≈ −0,20 USDT) — **protección activa confirmada**
- Patrimonio ≈991,42 (con abiertas) → **990,81** (todo en cash)

Órdenes FILLED = trades (integridad OK).

## 2–3. Causas cuantificadas (hechos)

| Fuente | Impacto USDT | n |
|---|---:|---:|
| Salidas por tendencia debilitada | **−6,11** | 47 |
| Stop-loss (−1%) | **−4,11** | 4 |
| Take-profit (+2%) | **+2,41** | 5 |
| Comisiones | −2,78 | — |
| Slippage | −1,39 | — |

Cerradas: **56** · Wins **7** / Losses **49** · WR **12,5%** · PF **0,25** · Expectativa **−0,14**/op

### Por mercado

| Mercado | Cerradas | P/L |
|---|---:|---:|
| ETH | 25 | −3,68 |
| SOL | 16 | −2,54 |
| BTC | 15 | −1,58 |

### Hipótesis (no hechos)

1. Ruido de 1m provoca salidas prematuras (`trend_break`).
2. El movimiento medio capturado no cubre fee+slip.
3. Entradas 4/5 pueden llegar tarde al impulso.

## 4. Hipótesis de mejora (congeladas)

| ID | Idea | Estado |
|---|---|---|
| U1_TREND15 | Confirmar tendencia 15m | research / frozen |
| U2_PULLBACK | Entrar en retroceso | research / frozen |
| U3_ATR_EXITS | SL/TP por ATR + filtro costo | research / frozen |
| U4_COOLDOWN | Menos operaciones repetitivas | research / frozen |

**A y B no se modificaron.**

## 5–7. Backtest walk-forward (900×1m, fee+slip, OOS 30%)

Archivo: `docs/etapa_u_backtest.json`

**Fuera de muestra (ninguna rentable):**

| Variante | Neto OOS | Compras | WR | PF |
|---|---:|---:|---:|---:|
| A baseline | −3,13 | 22 | 0% | 0 |
| U1 tendencia 15m | 0,00 | **0** | — | — |
| U2 pullback | −2,49 | 17 | 0% | 0 |
| U3 ATR | −0,59 | 3 | 0% | 0 |
| U4 cooldown | −0,78 | 8 | 0% | 0 |

`declare_profitable: false` · `declare_winner: false`  
U1 **no opera** en OOS (válido reportar “sin operaciones”).  
Menos pérdidas ≠ estrategia ganadora.

## 8. IA

- 264 predicciones RESOLVED · calibración **0**
- Modelo research validado · `validated_for_paper_ai=false`
- **No autorizar ejecución** · PAPER_AI off

## 9. Candidatas a investigación prospectiva

Solo observación futura (sin activar):

1. U4 (menos frecuencia) — menor daño bruto en esta ventana, aún negativo  
2. U1 — demasiado restrictiva aquí (0 trades OOS)  
3. U3 — pocas operaciones; necesita más muestra  

**Ninguna lista para dinero (ni paper operativo nuevo) sin evidencia prospectiva.**

## 10. Riesgos

Sobreajuste, optimizar win-rate sin expectativa, quitar stops, subir exposición, activar IA sin calibración.

## 11. Pruebas

`test_etapa_u_research` + economic + stop protections → **9 passed** (suite U-related)

## 12–13. Docker e integridad

Servicios Up; A STOPPED; B STOPPED 1000; lab/research/express intactos; sin órdenes reales.

## 14. Dashboard

Inicio → «¿Cómo le está yendo a mi bot?» + «¿Cómo podemos mejorar mi bot?»  
API: `/api/research/improve` · `/api/research/backtest-u`

## 15. Rollback

```text
git checkout checkpoint-etapa-u-pre-20261110_103023
# DB: pg_restore desde backups/paper_pre_etapa_u_*.dump (sin borrar volúmenes)
```
