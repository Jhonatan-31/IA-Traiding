# AK — Auditoría del motor de simulación original (V1)

## Componentes

| Área | Implementación | Estado |
|------|----------------|--------|
| Precio paper/demo/active | `prospect/execution.estimate_fill_price` desde mid/mark | Comprobado |
| Research D28H5 | `simulate_ledger` al **close** + `COST_FRAC` | Congelado |
| Fee | Embebida en precio all-in (`px * (1±fee)`) | Comprobado; AD corrigió doble conteo cash |
| Spread | Proxy `spread_bps` (mitad cada lado) — **sin BBO** | Heurístico |
| Slippage | `base_slip_rate` + factor vs `bar_volume` | Heurístico |
| Impacto | No modelado con profundidad real | Ausente |
| Fills parciales | Cap 25% bar volume si frac>0.25 | Parcial |
| Book | Solo si caller pasa `order_book`; paper path casi nunca | Preparado / no usado |
| Bid/ask live | No en market-stream (solo aggTrade) | Ausente pre-AK |
| Vision Parquet | Solo OHLCV; omite quote/trades/taker_buy | Pérdida documentada |

## Supuestos optimistas

1. Mid/close ≈ ejecutable.  
2. Spread 1–2 bps fijo válido en todo régimen.  
3. Slip fijo basta para tamaño retail.  
4. Un fill consume liquidez sin caminar el libro.  
5. Sin latencia de red ni cola de órdenes.

## Inconsistencias

- Research usa `spread/20000` en `COST_FRAC`; `estimate_fill_price` usa `spread/10000` como half-spread (equivalente a 2× half en buy+sell round-trip si se interpreta distinto).  
- Fee en precio all-in vs fee reportada por separado: correcto tras AD en engines paper; research atribuye por shares del COST_FRAC.

## Qué mejora AK (V2) sin reemplazar V1

- BBO bookTicker con edad/stale.  
- BUY=ask / SELL=bid.  
- Cap por top qty.  
- Comparación explícita V1 vs V2.  
- Vision ext sidecar no destructivo.
