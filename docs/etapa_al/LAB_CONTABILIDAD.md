# AL1 — Contabilidad Lab SELL (forense)

## Hallazgo

**CONFIRMADO:** con `fill_price` all-in de V1 (`estimate_fill_price` SELL ya neto de fee), el ledger Lab restaba la comisión otra vez al acreditar cash → doble fee.

## Flujo (post-corrección)

1. Proceeds brutos implícitos en modelo V1 → precio all-in neto.
2. Comisión: registrada en `lab_trades.fee` (informativo / reporting).
3. Moneda: cotizada (USDT) en el modelo actual.
4. Proceeds netos = `qty * fill_price` cuando `fill_price_is_all_in=True`.
5. Cash += net (sin segundo débito de fee).
6. Inventario: DELETE posición.
7. Fill + fee + slip + realized_pnl en `lab_trades`.
8. Patrimonio: cash + cost basis restante.

## Corrección

- `ledger.apply_sell`: `net = proceeds` si all-in; fee solo reporting.
- `executor`: pasa `fee_component*qty` y `fill_price_is_all_in=True`.

## Impacto histórico

Registros Lab previos **no reescritos** (autorización requerida). Riesgo residual: SELLs históricos pueden haber sub-acreditado cash. Documentado como incidente contable; balances productivos no se “arreglan” en silencio.

## Tests

`backend/tests/test_etapa_al_lab_fee.py` — DB aislada en memoria.
