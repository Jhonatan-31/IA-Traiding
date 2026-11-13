# AA1 — Prerregistro (antes de observar resultados del período nuevo)

Fecha de registro: 2026-11-13 · Commit base `614bb9d` · Hash `5326edb8a539cfe5`

## Hipótesis principal

En el período temporal **post-2025-10** (candidato 2025-11-01 → 2026-10-31, sujeto a disponibilidad), la configuración congelada **Z-TSMOM-D28H5** produce **exceso de retorno neto** frente al benchmark primario **Z-BH-EQ** (equiponderado Spot con rebalance diario y mismos costos), con drawdown no desproporcionado.

## Hipótesis nula

El exceso neto frente a Z-BH-EQ es ≤ 0, o cualquier aparente ventaja es frágil (costos, concentración, régimen).

## Benchmarks

| Rol | ID | Definición exacta |
|-----|-----|-------------------|
| **Primario** | Z-BH-EQ | 1/3 BTC+ETH+SOL, rebalance diario al close, mismos fee/slip/spread |
| Secundario | Z-BH-BTC | 100% BTC hold (un solo fill inicial) |
| Secundario | Cash | 0 neto |

Nota: BH-EQ **con** rebalance diario ≠ buy-and-hold estático sin rebalance; usamos el primero (idéntico al de Z).

## Métrica primaria

Exceso neto = `net_D28H5 − net_BH_EQ` (USDT, capital 1000).

## Métricas secundarias

Drawdown máx., exposición media/máx., turnover_events, fees, días en cash, sharpe_proxy, sensibilidad costos (+50% fricciones), dependencia del mejor mes/activo.

## Costos (congelados)

fee 10 bps · slip 5 bps · spread proxy 1 bp · sin cambiar tras ver resultados.

## Reglas de aceptación → CANDIDATA PARA REVISIÓN DE PRUEBA PROSPECTIVA PAPER

Todas:

1. Configuración/hash idénticos a Z.
2. Datos íntegros; sin look-ahead en fixtures.
3. Exceso neto > 0 vs BH-EQ.
4. Stress de costos: exceso o neto D28H5 aún razonable (stress neto D28H5 > 0 y no colapso vs BH-EQ).
5. Drawdown ≤ 1.5 × DD de BH-EQ (o justificación documentada).
6. No dependencia exclusiva de ≤3 días o un solo activo (>80% del exceso).
7. Sin hallazgos adversariales críticos.
8. Independencia del período al menos «nueva con independencia parcial» o mejor.

## Reglas de rechazo → RECHAZADA

- Exceso neto ≤ 0.
- Fallas críticas de motor/datos/look-ahead.
- Fragilidad extrema a costos o a un mes/activo.
- Riesgo claramente inaceptable vs benchmark.

## Insuficiencia → INCONCLUSA

- Datos incompletos / independencia dudosa.
- Muestra demasiado corta para interpretar.
- Ambigüedad (exceso pequeño dentro de incertidumbre amplia).

## Período y universo

- Universo: BTCUSDT, ETHUSDT, SOLUSDT Spot.
- Candidato: 2025-11-01 → 2026-10-31 (UTC), **corte registrado al confirmar última barra disponible**.
- Warm-up lookback: usar historial previo ya ingerido (≤2025-10-31) solo para indicadores; **métricas de evaluación solo en el período nuevo**.

## Política de datos faltantes

No fabricar velas. Si faltan meses: acortar el período evaluable y degradar independencia/insuficiencia según cobertura.

## Independencia (a auditar en AA2, sin mirar retornos)

Clasificar tras inventario de uso previo; no declarar «virgen» solo por no estar descargado.
