# INFORME — Etapa AL PRO

## A. VEREDICTO

**V2 MEJORADO CON LIMITACIONES**

V2 es apto para **investigación aislada** y comparación controlada frente a V1.  
No está validado para reemplazar motores paper ni migrar carteras: falta profundidad, BBO histórico y evidencia longitudinal de captura.

## B. CONTABILIDAD LAB

| Campo | Valor |
|-------|--------|
| Hallazgo | Doble comisión en SELL Lab cuando `fill_price` es all-in V1 |
| Causa | `apply_sell` restaba fee tras acreditar precio ya neto |
| Impacto | Cash Lab sub-acreditado en SELLs afectados (histórico **no** reescrito) |
| Corrección | `fill_price_is_all_in=True` → credit `qty*price`; fee solo reporting; executor alineado |
| Tests | `test_etapa_al_lab_fee.py` |
| Riesgo residual | Filas históricas Lab pueden estar sesgadas; requiere autorización para ajuste |

## C. CALIDAD BBO

- Campos: símbolo, update_id, bid/ask + qty, received_at_ms, mono_ns, connection_id, sync_state, fresh/stale, reject reasons.
- `exchange_ts_ms` **no inventado** si el stream no lo provee.
- Top-of-book ≠ order book sincronizado.
- Captura 24/7 **no** activada; plan + endpoint acotado manual.

## D. COMPARACIÓN V1/V2

- Módulo `compare_experiment` + API `compare-once`.
- Sin BBO → `NO_COMPARABLE` (sin sustitución silenciosa).
- Observaciones de mediana: solo las generadas en sesión/API; este informe **no inventa N**.
- Peor precio V2 ≠ prueba de superioridad económica.

## E. DATOS HISTÓRICOS (Vision)

- Parser enriquecido: quote_volume, n_trades, taker buy base/quote.
- Sidecar `*_vision_ext.parquet` no reemplaza OHLCV V1.
- Prueba pequeña no destructiva en tests (parser+audit; Parquet si hay pyarrow).

## F. D28H5

- Hash `5326edb8a539cfe5` intacto; sin recalibrar parámetros/señales.
- Costos históricos = close + proxy V1; sin BBO pasado → **no** recomparación directa V2.
- Veredicto mantiene: **POSIBLE VENTAJA INCREMENTAL, AÚN NO VALIDADA**.

## G. OPERACIÓN

- A/B STOPPED · PAPER_ONLY · PAPER_AI OFF · AB-PROSPECT PREPARED_DISABLED.
- V2 no muta ledgers · sin órdenes reales · sin claves privadas Binance.
- EBZ: verificar carrier Ethernet en despliegue; NO-CARRIER histórico no se asume vigente sin lectura actual.
- Consultate / EVS no tocados.

## H. ENTREGA

| Artefacto | Valor |
|-----------|--------|
| Commit | `f98d530` |
| Pre-tag | `checkpoint-etapa-al-pre-20261117_152000` |
| Tag final | `checkpoint-etapa-al` |
| Rollback | `git checkout checkpoint-etapa-al-pre-20261117_152000` (código); no `down -v` |
| Dashboard | `/calidad-ejecucion` ampliado |
| API | compare-once, capture/plan, capture/run-bounded, audit lab note |
| Tests | `test_etapa_al*.py` + regresiones AK |
| Docs | `docs/etapa_al/*` |

## I. DECISIÓN POSTERIOR

1. Autorizar grabación prospectiva **acotada** de BBO (sí, con límites).  
2. Ampliar profundidad solo con autorización (no fabricar L2).  
3. Contabilidad Lab: corrección forward hecha; ajuste histórico pendiente de autorización.  
4. **Mantener V2 aislado** para paper/migración hasta evidencia longitudinal.

**No migrar carteras a V2 sin autorización específica.**
