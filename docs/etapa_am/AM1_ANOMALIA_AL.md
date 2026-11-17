# AM1 — Comparación anómala AL (V2 “más barato”)

## Observación histórica AL

- BUY 0.001 BTCUSDT
- V1 ≈ 64159.14 · V2 all-in ≈ 64095.06 · Δ ≈ −64.08 USDT/BTC

## ¿Auditable como movimiento de mercado?

**NO.** Timestamps originales de V1/V2 no quedaron persistidos como par reproducible con edades de vela/trade. Se clasifica la observación AL como **NO AUDITABLE** para “movimiento entre muestras”, y se **reconstruye** con las fórmulas de código + números reportados.

## Causa primaria (reconstrucción)

| Motor | Fórmula BUY | Defaults |
|-------|-------------|----------|
| V1 | `(mid + mid·spread_bps/1e4 + mid·slip)·(1+fee)` | slip=**0.001**, spread_bps=**2**, fee=0.001 |
| V2 | `(ask·(1+extra_slip))·(1+fee)` | extra_slip=**0.0002**, fee=0.001 |

Con mid≈ask (spread vivo ~0.01 USDT), el slip proxy V1 de 10 bps domina frente al extra_slip V2 de 2 bps → V2 all-in **parece** más barato. **No** demuestra superioridad económica de V2.

## Endpoint

`GET /api/execution-quality/al-anomaly`
