# INFORME — Etapa AN PRO

## VEREDICTO

**COMPARACIÓN NORMALIZADA CON LIMITACIONES**

Contrato `cost_contract_v1` + dos modos reproducibles (LEGACY / MATCHED).  
V2 **no** listo para migrar PAPER. Evidencia suficiente para decidir: **seguir observando ejecución (BBO/WS) sin órdenes**, no volver aún a optimizar señales.

## RESULTADOS

### AN0 — Independencia AM

- 60 buckets = `(símbolo × ventana 30s)`, **no** 360 muestras independientes.
- 360 filas = 60 × 2 lados × 3 tamaños (**derivadas, correlacionadas**).
- Intervalo REST mediano ≈ **3,68–3,69 s** por símbolo (poll 2s + RTT secuencial).
- `update_id` en AM REST: **0** (bookTicker REST sin `u`).

### LEGACY (AM dataset, por símbolo|lado)

| Grupo | Buckets | mediana diff bps V2−V1* |
|-------|---------|-------------------------|
| BTC BUY | 20 | **≈ −10.01** |
| BTC SELL | 20 | **≈ +9.99** |
| ETH BUY | 20 | ≈ −9.98 |
| ETH SELL | 20 | ≈ +9.96 |
| SOL BUY | 20 | ≈ −9.32 |
| SOL SELL | 20 | ≈ +9.31 |

\*Convención: bps de `price_v2 − price_v1` vs mid (BUY negativo ⇒ V2 más barato unitario bajo defaults).  
**Causa dominante:** V1 `base_slip=10 bps` vs V2 `extra_slip=2 bps` — **no** el BBO.

### MATCHED (mismo fee 10 bps + slip 2 bps; V1=mid, V2=ask/bid)

| Grupo | mediana diff bps |
|-------|------------------|
| BTC BUY/SELL | ≈ **±0.0008** |
| ETH BUY/SELL | ≈ **±0.028** |
| SOL BUY/SELL | ≈ **±0.69** |

**Atribuible al bid/ask observado** (mid→touch). SOL mayor en bps por spread tick / precio.  
Cash adverso ponderado MATCHED ≈ **+0.01 USDT** (despreciable vs LEGACY ≈ −0.4 USDT por asimetría de supuestos).

### Tamaños 25/100/500 USDT

Casi sin `incomplete_without_l2` (1 caso ETH SELL en AM). Top-of-book **suficiente** para estos notionals en la ventana observada — **no** justifica L2 aún.

## CAPTURA AN (dual REST∥WS, 180 s máx.)

| Fuente | Eventos | Duración | Stop | Bytes |
|--------|---------|----------|------|-------|
| REST | 138 | 180.4 s | max_seconds | 96 KiB |
| WS bookTicker | **20 000** | **65 s** | **max_events** | ~10.4 MiB |

- Rate WS ≈ **308 msg/s** (push); REST ~0.77 evt/s/símbolo.
- Reconexiones WS: 0.
- Fair economics REST vs WS (tras buckets): **casi idénticos** → más mensajes WS = continuidad, **no** fills más “verdaderos”.
- Sin L2 · sin permanente · sin autostart.

## LAB

- 16 SELLs · 0 CONFIRMADO · 16 PROBABLE · 0 DESCARTADO.
- Impacto estimado ≈ **0.395 USDT** (incierto sin cash trail).
- Falta para CONFIRMADO: cash before/after, commit del executor, flag all-in persistido.
- **Sin regularización.**

## SEGURIDAD

A/B STOPPED · PAPER_ONLY · D28H5 intacta · V2 aislado · ledgers intactos · Consultate/EVS OK · `eno1` NO-CARRIER · Wi‑Fi UP.

## ENTREGA

| Artefacto | Valor |
|-----------|--------|
| Código | `672026c` (+ fix UI `635dd6b`) |
| Pre-tag | `checkpoint-etapa-an-pre-20261117_164906` |
| Tag | `checkpoint-etapa-an` |
| Backup | `paper_ebz_20261117_215354` |
| Dataset | `/artifacts/history/etapa_an/` |
| Contrato | `docs/etapa_an/COST_CONTRACT_V1.md` |
| Tests | `test_etapa_an.py` (25 passed, 1 skipped local sin websockets) |

## RECOMENDACIÓN FINAL

**B. V2 está listo para una futura revisión de observación prospectiva sin órdenes.**

- LEGACY vs MATCHED ya separan “supuestos” de “BBO”.
- WS mejora continuidad frente a REST.
- L2 **no** justificado aún para 25–500 USDT en la evidencia actual.
- **No migrar carteras** sin autorización y más ventanas de mercado.

### Adversarial (AN8) — respuestas breves

| Pregunta | Evidencia |
|----------|-----------|
| ¿V2 “mejor” solo por menos slip? | **Sí en LEGACY** (~10 bps). |
| ¿MATCHED aísla BBO? | **Sí** (~0–0.7 bps). |
| ¿360 independientes? | **No.** |
| ¿Doble fee/spread? | Contrato v1 + tests; Lab SELL forward OK. |
| ¿WS ⇒ mejor fill? | **No**; solo más updates top-of-book. |
| ¿Estimaciones = fills reales? | **No** — etiquetado hipotético. |
