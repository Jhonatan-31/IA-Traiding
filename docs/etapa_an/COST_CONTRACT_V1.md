# Contrato económico `cost_contract_v1`

## Identidad

- ID: `cost_contract_v1`
- Versión: `1.0.0`
- Código: `backend/app/execution_v2/cost_contract.py`

## Reglas

1. Si se compra al **ask**, mid→ask **ya** es el medio spread observado; no sumar proxy de spread encima.
2. Si `fill_price_is_all_in`, el efectivo es `qty × price`; **no** restar fee otra vez.
3. `extra_slip` es **supuesto** salvo medición explícita.
4. Sin L2, qty > top-of-book ⇒ estimación **incompleta** (no fill completo inventado).
5. Reportar siempre precio unitario **y** nocional/cash.

## BUY

```
touch = ask                    # o mid + proxy_half_spread
raw   = touch × (1 + slip)
all_in = raw × (1 + fee)
cash_out = qty × all_in
```

## SELL

```
touch = bid                    # o mid − proxy_half_spread
raw   = touch × (1 − slip)
all_in = raw × (1 − fee)
cash_in = qty × all_in         # fee ya embebido
```

## Modos de comparación

| Modo | Qué mide |
|------|----------|
| LEGACY | Defaults V1 (slip 10 bps + spread 2 bps) vs V2 (extra_slip 2 bps) |
| MATCHED | Mismo fee+slip; V1 desde mid sin proxy spread vs V2 ask/bid → valor del touch BBO |
