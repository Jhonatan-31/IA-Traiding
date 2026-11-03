# G.1 — Auditoría de métricas (Etapa F → G)

## Unidades de `net_return`

| Campo | Unidad | Interpretación |
|-------|--------|----------------|
| `net_forward_return(entry, exit)` | **fracción por operación** | `(sell/buy) - 1` con fee+slip ida y vuelta. Ej. `−0.004` ≈ −0.4% sobre el notional de esa operación. |
| `trade_stats.net_return_sum` | **suma de fracciones por trade** | Σ r_i sobre trades tomados. **No** es el rendimiento de una cartera con capital fijo. Trades solapados se suman como si fueran independientes. |
| `trade_stats.avg_trade` / `expectancy` | media de fracciones por trade | E[r] por operación tomada. |
| `trade_stats.max_drawdown` | drawdown de la **curva Σ r_i** | Peak-to-trough de la suma acumulada de fracciones, no del equity de cuenta. |
| `aggregate_strategy_table.mean_net_return_sum` | media entre folds de `net_return_sum` | Promedio de sumas de fracciones por fold. Magnitudes grandes (p.ej. −21) son sumas de miles de trades, no −2100% de capital. |
| Shadow `mean_net_return` | media de `observed_net_return` | Incluye filas HOLD con label hipotético long. **No** es PnL de estrategia ejecutable. |

## Intervalos de confianza (Etapa F)

- `bootstrap_ci` hacía bootstrap i.i.d. sobre trades o sobre folds.
- Trades en el mismo activo/tiempo están **dependientes**; mercados están correlacionados.
- Etapa G introduce `block_bootstrap_ci` (bloques temporales) y advierte que CI i.i.d. **sobreestiman** precisión.
- Con n_folds=2 el IC entre folds es frágil; no usar como prueba de edge.

## Profit Factor y drawdown

- PF = sum(gains) / sum(|losses|) sobre fracciones por trade (OK si se declara).
- DD de suma de fracciones ≠ DD de cartera. El simulador G.6 reporta DD sobre equity de cuenta.

## Benchmarks

- Misma etiqueta (horizonte 6×1h), mismos fee/slip 0.1%+0.1%.
- Etapa F ejecutaba en el **cierre de la vela de decisión** (sesgo optimista).
- Etapa G ejecuta por defecto en el **open de t+1** tras señal en close de t.

## Calibración isotónica y LogLoss

- Isotónica minimiza Brier/ECE en validación; puede **empeorar LogLoss** en test (colas / clipping).
- No implica mejor edge económico. G.5 usa retorno esperado neto, no solo P(up).

## Conclusión operativa

Comparar solo magnitudes compatibles: portfolio equity % vs portfolio equity %; fracción/trade vs fracción/trade.
No promover PAPER_AI con métricas Etapa F mal interpretadas.
