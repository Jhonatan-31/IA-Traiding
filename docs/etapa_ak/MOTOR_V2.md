# AK — Motor virtual V2

**Versión:** `execution_v2.1`  
**No muta ledgers. No activa A/B. No sustituye resultados D28H5.**

## Flujo

```
bookTicker público → BboRegistry (edad, stale)
                 ↓
simulate_fill_v2(side, qty, bbo)
                 ↓
BUY: ask (+slip)(+fee) | SELL: bid (−slip)(−fee)
                 ↓
partial si qty > top qty | reject si stale/missing
```

## API

- `GET /api/execution-quality/status`
- `POST /api/execution-quality/bbo/refresh`
- `POST /api/execution-quality/simulate`
- `GET /api/execution-quality/d28h5-costs`

## Rollback

Desactivar UI/ruta o revertir commit AK. V1 `estimate_fill_price` permanece intacto en demo/active/lab.
