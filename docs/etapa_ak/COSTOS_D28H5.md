# AK — Reconciliación costos D28H5 (~72.733833 USDT)

## Identidad (motor research V1 congelado)

```
COST_FRAC = fee(0.001) + slip(0.0005) + spread_bps/20000(0.00005) = 0.00155
total ≈ notional_traded × COST_FRAC
46925.0539 × 0.00155 ≈ 72.7338
```

Split reportado (AC):

| Componente | USDT | Share |
|------------|------|-------|
| Fee | 46.925054 | FEE_RATE/COST_FRAC |
| Slip | 23.462527 | SLIP_RATE/COST_FRAC |
| Spread | 2.346253 | (0.5bp)/COST_FRAC |
| **Total** | **72.733833** | |

Actividad: 189 rebalances_real · 356 turnover_events · 179 buys · 177 sells.

## Qué NO significa

- No es solo “comisión Binance”.  
- No valida holdout de nuevo (consumido).  
- V2 no recalcula D28H5 automáticamente.

Hash freeze: `5326edb8a539cfe5` · parámetros intactos.
