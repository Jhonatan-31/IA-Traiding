# Matriz de hallazgos AC

| ID | Pri | Título | Acción |
|---|---|---|---|
| AC-F01 | P0 | Runners protección Exited(137) | Alertar; no auto-start; alinear política |
| AC-F11 | P0 | Compra sin rollback si falla posición | Transacción + refund (etapa ledger) |
| AC-F12 | P0 | B omite salidas si no autorizado | Salidas antes del gate de entradas |
| AC-F02 | P1 | Parquet sin taker/quote Vision | Migración no destructiva |
| AC-F03 | P1 | Simulador sin BBO | Modelo ejecución versionado |
| AC-F04 | P1 | Sin detector suspensión host | SLI gap heartbeats |
| AC-F05 | P1 | Costos rotación 72.73 | Hipótesis bandas (no holdout) |
| AC-F13 | P1 | Doble fee cash demo/active | Unificar modelo fee |
| AC-F14 | P1 | Dedupe trade_id eviction | LRU/test >4096 |
| AC-F06–F09 | P2 | Prospect/obs/min_hold/+90.75 | Ver findings.py |
| AC-F15 | P2 | Express sin LAB_CONTROL_TOKEN | Alinear auth |
| AC-F10 | P3 | Red local / token (fortaleza) | Mantener |

Fuentes adicionales: auditorías explore market-stream, inventario y riesgo/ledgers.  
Detalle: `backend/app/research/etapa_ac/findings.py`.  
**No corregidos en AC** (política: no tocar ledgers/semántica B sin etapa dedicada).
