# Informe económico AC (reconciliación AB)

Holdout AA consumido — análisis descriptivo.

## Identidades

```
d28 = market(BH-EQ) + (EXP-MATCH − BH-EQ) + (D28 − EXP-MATCH)
−126.4242 = −398.3244 + 179.0705 + 92.8297
residual = 0
```

Costos ya están dentro de cada neto. No restar 72.733833 otra vez.

```
fee+slip+spread = 46.925054 + 23.462527 + 2.346253 = 72.733834 ≈ 72.733833
```

## Definiciones de actividad

- **rebalances_real (189)**: días con ≥1 ajuste \|Δ\|≥1 USDT.
- **turnover_events (356)**: ajustes por símbolo (no round-trips cerrados).
- **buys/sells (179/177)**: lados de esos ajustes.

## Vs FIXED-55

+90.7526 USDT con exposición media casi idéntica (~55%). Evidencia de posible timing/selección, **sin** validación prospectiva ni superioridad vs efectivo.

Sensibilidad aproximada: fees×2 ⇒ neto ≈ −126.42 − 72.73 = −199.15 (peor).
