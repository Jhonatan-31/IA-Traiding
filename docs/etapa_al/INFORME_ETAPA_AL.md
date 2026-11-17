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
- Observación post-deploy EBZ (BUY 0.001 BTCUSDT, 2026-11-17):
  - comparable: **1**
  - precio V1 ≈ 64159.14 · V2 all-in ≈ 64095.06
  - no comparable en esa corrida: **0**
  - N total de esta verificación: **1** (no inventar series)
- Peor/mejor precio V2 ≠ prueba automática de superioridad económica.

## E. DATOS HISTÓRICOS (Vision)

- Parser enriquecido: quote_volume, n_trades, taker buy base/quote.
- Sidecar `*_vision_ext.parquet` no reemplaza OHLCV V1.
- Prueba pequeña no destructiva en tests (parser+audit; Parquet si hay pyarrow).

## F. D28H5

- Hash `5326edb8a539cfe5` intacto; sin recalibrar parámetros/señales.
- Costos históricos = close + proxy V1; sin BBO pasado → **no** recomparación directa V2.
- Veredicto mantiene: **POSIBLE VENTAJA INCREMENTAL, AÚN NO VALIDADA**.

## G. OPERACIÓN

- demo=STOPPED · active=STOPPED · PAPER_ONLY · V2 no muta ledgers.
- EBZ 2026-11-17 post-deploy: `eno1` DOWN **NO-CARRIER**; `wlp7s0` UP · IP `192.168.1.12` · gateway `192.168.1.254`.
- market-stream healthy · API healthy · BBO refresh público OK.
- Consultate / EVS intactos (Up ~21h).
- Backups pre-AL: `paper_ebz_20261117_201956` (y `201611`).

## H. ENTREGA

| Artefacto | Valor |
|-----------|--------|
| Commit | `762d1de` (docs) / `f98d530` (código AL) |
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
