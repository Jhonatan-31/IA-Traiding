# AL0 — Auditoría motor V2

## Matriz

| CAPACIDAD | IMPLEMENTACIÓN | EVIDENCIA | LIMITACIÓN | TEST |
|-----------|----------------|-----------|------------|------|
| Entrada side/qty/ref/BBO | `simulate_fill_v2` | `engine_v2.py` | Sin profundidad L2+ | `test_etapa_al.py` |
| BUY→ask / SELL→bid | Sí | engine | Top-of-book only | fresh_bbo |
| Fee taker | `fee_rate` en all-in | engine | Hipótesis retail 10 bps | lab_fee + al |
| Slip extra | `extra_slip_rate` | engine | Hipótesis, no medida exchange | al |
| Stale reject | `max_quote_age_ms` | engine + registry | Edad local recepción | stale_bbo |
| Top qty / parcial | cap a bid/ask qty | engine | Sin niveles adicionales | excessive_qty |
| Qty cero / depth 0 | reject | engine | No inventa profundidad | missing_depth |
| Mid fallback | opt-in `allow_mid_fallback` | engine | Marcado UNCERTAIN | API body |
| Patrimonio | No muta ledgers | api `mutates_ledgers=false` | Solo simulación | audit-summary |
| BBO registry | bookTicker público | `bbo_store.py` | No order book sync | duplicate/ooo |

## Hipótesis vs observación

| Elemento | Tipo |
|----------|------|
| bid/ask/qty frescos | Observación (bookTicker público) |
| `received_at_ms` / mono_ns | Observación local |
| `exchange_ts_ms` | Solo si el stream lo trae — **no inventado** |
| fee_rate / extra_slip | Hipótesis de modelo |
| assumed_send_latency_ms | Análisis etiquetado, no RTT Binance |
| Fill exchange real | **No** — simulación virtual |
