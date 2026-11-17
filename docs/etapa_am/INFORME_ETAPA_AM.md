# INFORME — Etapa AM PRO

## A. VEREDICTO

**EXPERIMENTO V1/V2 VALIDADO CON LIMITACIONES**

Una captura acotada con BBO público contemporáneo demuestra diferencias **medibles** entre V1 (mid+proxy) y V2 (ask/bid), dominadas por **supuestos de fricción distintos**, no por “ventaja” de V2.  
V2 sigue **aislado**. No migrar PAPER.

## B. CAPTURA

| Campo | Valor |
|-------|--------|
| Experimento | `AM-BBO-1794948090` |
| Inicio→fin | 601064 ms (~10.0 min) |
| Límite autorizado máx. | 30 min / 100 MB / 250k |
| Límite aplicado | **600 s** / 50 MB / 910 eventos (reducido: Wi‑Fi only, `eno1` NO-CARRIER) |
| Stop | `max_seconds` |
| Símbolos | BTCUSDT, ETHUSDT, SOLUSDT (156 eventos c/u) |
| Eventos | **468** · duplicados 0 · inválidos 0 · errores 0 |
| Bytes | 328030 (~321 KiB) |
| Huecos | heurística 432 vs teórico 900 polls×sym; polls reales=156 (latencia REST en bucle) — **cobertura incompleta vs plan ideal, no relleno** |
| Permanente | **No** |
| Dataset | `/artifacts/history/etapa_am/bbo_capture_1794948090084.jsonl` |
| Manifest | `docs/etapa_am/bbo_capture_1794948090084.manifest.json` |

## C. COMPARACIÓN V1/V2

### AM1 — observación AL única

- Clasificación: **NO AUDITABLE** como movimiento de mercado (sin timestamps originales emparejados).
- Reconstrucción: V1 slip default **10 bps** + spread 2 bps vs V2 extra_slip **2 bps** → V2 all-in ~64 USDT/BTC “más barato” en BUY 0.001.
- Causa: **mismatch de supuestos**, no prueba de superioridad.
- Endpoint: `/api/execution-quality/al-anomaly`.

### Experimento AM (anti-pseudorreplicación, buckets 30 s)

| Métrica | Valor |
|---------|--------|
| Eventos raw | 468 |
| Buckets independientes | 60 |
| Filas (BUY/SELL × 3 tamaños) | 360 |
| Comparables | **360 (100%)** |
| No comparables | **0** |
| Spread abs mediana | ~0.01 USDT |
| Diff precio mediana V2−V1 | ≈ −6.7e-5 (BUY+SELL mezclados) |
| Cost gap adverso mediana | ≈ −0.10 USDT (V2 “mejor” bajo V1 pesimista) |
| Tamaños 25/100/500 USDT | mediana diff similar; **1** warning liquidez en n500 |
| Extremas \|diff\| | ~±64 USDT/BTC (mismo efecto slip V1 en BTC) |

**Interpretación:** con defaults actuales, V1 carga ~10 bps de slip proxy que V2 no replica; el BBO vivo aporta spread real ~0–1 tick. No declarar rentabilidad ni equivalencia a fill Binance.

## D. CONTABILIDAD LAB

| Campo | Valor |
|-------|--------|
| SELLs examinados | **16** (`lab_auto`) |
| CONFIRMADO | 0 |
| PROBABLE | **16** |
| NO_DETERMINABLE | 0 |
| Periodo | 2026-11-13 → 2026-11-17 |
| Impacto estimado | **≈ 0.395 USDT** undercredit agregado |
| Regularización | **No ejecutada** (propuesta documentada en API) |
| Ledgers | **intactos** |

## E. VISION

- Parser conserva quote_volume, n_trades, taker buy base/quote.
- Timestamps: detección ms vs µs (`normalize_vision_open_time_ms`); sin reingesta masiva.
- OHLCV V1 no modificado.

## F. OPERACIÓN

- demo=STOPPED · active=STOPPED · PAPER_ONLY · V2 aislado.
- `eno1` DOWN NO-CARRIER · `wlp7s0` UP · Binance público HTTP 200.
- Consultate/EVS intactos · D28H5 hash `5326edb8a539cfe5` sin tocar.
- Sin órdenes reales · sin captura 24/7.

## G. ENTREGA

| Artefacto | Valor |
|-----------|--------|
| Código AM | `7f88c08` |
| Pre-tag | `checkpoint-etapa-am-pre-20261117_153500` |
| Tag | `checkpoint-etapa-al` intacto; `checkpoint-etapa-am` al cierre |
| Backup | `paper_ebz_20261117_204128` |
| Tests | `test_etapa_am.py` (+ regresiones AL/AK) 44 passed |
| Dashboard | `/calidad-ejecucion` — sección experimento + anomalía + Lab RO |
| Rollback | revertir a pre-tag AM; **no** `down -v` |

## H. RECOMENDACIÓN

1. **Mantener V2 aislado.**  
2. Repetir mediciones en otras ventanas (autorización) — captura breve ≠ robustez multi-régimen.  
3. Antes de migrar PAPER: alinear documentación de supuestos V1/V2 (slip) o comparar con supuestos emparejados etiquetados.  
4. Autorizar por separado regularización Lab (~0.40 USDT estimado).  
5. Ethernet físico pendiente; no ampliar a L2 sin justificación.

**No migrar motores sin autorización específica.**
