# AL4 — Comparación controlada V1 vs V2

## Diseño

Misma `HypotheticalDecision` (ts, símbolo, side, qty, mid, fees/slip config, latencia asumida).

- V1: `estimate_fill_price` mid+proxy.
- V2: BBO fresco + modelo conservador.
- Sin BBO / stale → **NO_COMPARABLE** (nunca sustituye V1 en silencio).

## API

- `POST /api/execution-quality/compare-once`
- Módulo `compare_experiment.py` + `summarize_pairs`

## Interpretación

Peores precios V2 (ask más caro / bid más barato) **no** demuestran superioridad económica por sí solos: miden realismo del costo vs mid optimista.

## Observaciones

Las cifras de mediana se reportan solo tras corridas reales (dashboard/API). Este documento no inventa N.

## Limitaciones

- Top-of-book ≠ profundidad.
- Latencia de envío es etiqueta de análisis.
- Spread ya está en ask/bid; no se vuelve a sumar como “costo separado” en la narrativa de reconciliación.
