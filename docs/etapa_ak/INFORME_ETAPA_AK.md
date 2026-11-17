# INFORME — Etapa AK PRO

## VEREDICTO

**SIMULACIÓN MEJORADA CON LIMITACIONES**

Las operaciones paper/research V1 siguen siendo **ilustrativas con mid/close + fricción proxy**.  
V2 permite contrastar contra **BBO real** cuando hay bookTicker fresco, pero **no** hay BBO histórico para reescribir D28H5, ni profundidad completa, ni activación de bots.

## Qué tan confiable es hoy

| Escenario | Confiabilidad |
|-----------|----------------|
| Research D28H5 (close+proxy) | Útil para ranking relativo bajo costos congelados; **no** P/L “exchange-real” |
| Paper demo/active V1 | Mejor que close puro; aún optimista vs ask/bid |
| V2 con BBO fresco | Mejor estimación ejecutable spot taker top-of-book; limitada por top qty |
| Sin BBO / stale | V2 rechaza — correcto |

## Entregables

- Auditoría V1 · Motor V2 aislado · BBO registry + refresh público  
- Vision ext no destructivo · Reconciliación 72.73 · Tests adversariales  
- Dashboard `/calidad-ejecucion` · API `/api/execution-quality/*`

## Integridad

- A/B no activados por esta etapa  
- D28H5 / hash `5326edb8a539cfe5` sin recalibrar  
- AB-PROSPECT PREPARED_DISABLED  
- Ledgers no mutados por V2  
- V1 preservado para reconciliar

## Falta para evaluar más realista

1. Grabación prospectiva BBO/depth (no inventar pasado).  
2. Cable Ethernet estable en EBZ (NO-CARRIER previo).  
3. Re-ingesta Vision ext opt-in.  
4. Decisión explícita de migrar paper engines a V2 (autorización aparte).  
5. Alinear cash lab (posible doble fee en SELL) y pasar `order_qty`/`latency` reales si se unifica bajo V2.

## Entrega git

| Artefacto | Valor |
|-----------|--------|
| Tag | `checkpoint-etapa-ak` |
| Pre | `checkpoint-etapa-ak-pre-20261117_150800` |
| A/B | STOPPED (verificado EBZ) |
| PAPER_ONLY | Sí |
| Auth | OFF |

## Rollback

Revertir commit/tag AK. No requiere `down -v`.
