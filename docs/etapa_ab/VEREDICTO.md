# VEREDICTO FINAL — Etapa AB

## VEREDICTO

**POSIBLE VALOR ADICIONAL, AÚN NO VALIDADO**

## AUDITORÍA ECONÓMICA

Ventana: holdout AA 2025-11-01 → 2026-10-31 (descriptivo; **no** nueva prueba independiente).

| Referencia | P/L neto | DD | Exp. | Costos | Kind |
|---|---:|---:|---:|---:|---|
| D28H5 | **−126,42** | 29,6% | 55,5% | 72,73 | congelada |
| Efectivo | 0 | 0% | 0% | 0 | causal |
| BH-EQ diario | −398,32 | 57,7% | 99,6% | 3,29 | causal |
| BH-EQ hold (1 compra) | −400,91 | 57,2% | ~100% | 1,55 | causal |
| EXP-MATCH (media ex post) | −219,25 | 36,5% | 55,3% | 3,11 | **descriptivo** |
| FIXED-55 EQ | −217,18 | 36,2% | 54,8% | 3,11 | causal |
| VOL-SCALE EQ | −327,15 | 50,8% | 80,0% | 9,87 | causal |

### Atribución reconciliada (residual = 0)

| Componente | USDT |
|---|---:|
| Mercado plena exposición (BH-EQ) | −398,32 |
| Menor exposición media (descriptivo) | **+179,07** |
| Activo vs misma exposición media | **+92,83** |
| **Suma = D28H5** | **−126,42** |

- Vs FIXED-55 causal: **+90,75** (timing/selección más allá de exposición fija).
- Vs efectivo: **−126,42** (no aporta valor absoluto en esta ventana).
- Costos D28H5: 72,73 = fee 46,93 + slip 23,46 + spread 2,35; 189 rebalances reales; 356 turnovers; 179 buys / 177 sells.

## RESULTADO PROSPECTIVO

| Campo | Valor |
|---|---|
| Protocolo | `AB-PROSPECT-v1` |
| Hash | `5326edb8a539cfe5` |
| Estado | **PREPARED_DISABLED** |
| Inicio | no iniciado |
| Señales | 0 |
| Motivo | no forzar job que compita con runners; listo para activación explícita |

## SEGURIDAD

A STOPPED · B STOPPED · PAPER_ONLY · IA off · sin órdenes reales · ledgers intactos

## ENTREGA

- Pre: `checkpoint-etapa-ab-pre-20261113_101528`
- Post: `checkpoint-etapa-ab`
- Docs: `docs/etapa_ab/`
- Artefacto: `data/market_history/etapa_ab_results.json`
