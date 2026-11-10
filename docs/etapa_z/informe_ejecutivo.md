# Etapa Z PRO — Informe ejecutivo

## VEREDICTO

**EXISTEN HIPÓTESIS EXPLORATORIAS, SIN VALIDAR**

No hay candidata para validación prospectiva virtual: el holdout de Etapa W ya fue consumido y no existe período temporal virgen en el historial ingerido (nov-2024 → oct-2025).

## Qué investigamos

- Auditoría del laboratorio (datos 1m, agregación, causalidad).
- Literatura de TSMOM/CSMOM cripto con costos realistas.
- Horizontes diarios/4h, volatility targeting y rotación relativa BTC/ETH/SOL.
- Diagnóstico de microestructura y funding/OI (sin cargas masivas).

## Qué encontramos (OOS 20% comparable)

| Línea | Neto USDT | vs BH-EQ | Estado |
|-------|-----------|----------|--------|
| BH BTC | −56 | peor | benchmark |
| BH equiponderado | +202 | — | benchmark fuerte en esta ventana |
| **TSMOM 28d** | **+341** | **+139** | **exploratoria** |
| TSMOM + vol target | +28 | peor | descartada |
| RS top-1 | +406 | mejor | descartada (3 rebalances; N=3) |
| MOM 4h | +103 | peor / stress− | descartada |

## Qué descartamos

- Optimizar salidas intradía A (Etapa Y, no repetido).
- Microestructura con datos actuales (sin taker_buy en Parquet / sin book).
- CSMOM/rotación en universo de 3 como evidencia generalizable.
- MOM 4h tras costos (stress negativo).

## Qué podría merecer más estudio

**Z-TSMOM-D28H5** (long-only, lookback 28d): superó BH equiponderado y resistió stress de costos en el OOS interno. Sigue siendo **exploratorio** hasta:

1. Congelar reglas/hash.
2. Ingerir datos **posteriores a oct-2025** no usados.
3. Evaluar sin reajustar.

## Riesgos que permanecen

- Ventana OOS coincidió con alts > BTC (BH-EQ >> BH-BTC).
- Universo N=3.
- Sin BBO real; spread proxy.
- Sin holdout virgen.
- Sobreajuste de narrativa si se itera sobre el mismo span.

## Seguridad

A STOPPED · B STOPPED · PAPER_ONLY · PAPER_AI off · sin activación.
