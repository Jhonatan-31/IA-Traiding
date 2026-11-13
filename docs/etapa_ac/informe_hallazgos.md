# Matriz de hallazgos AC

| ID | Pri | Título | Acción |
|---|---|---|---|
| AC-F01 | P0 | Runners protección Exited(137) | Alertar; no auto-start en AC; alinear política |
| AC-F02 | P1 | Parquet sin taker/quote Vision | Migración no destructiva futura |
| AC-F03 | P1 | Simulador sin BBO | Modelo ejecución versionado aparte |
| AC-F04 | P1 | Sin detector suspensión host | SLI gap heartbeats |
| AC-F05 | P1 | Costos rotación 72.73 / 7.3% capital | Hipótesis bandas (no holdout) |
| AC-F06 | P2 | Prospect sin writer/job | Implementar antes de auth |
| AC-F07 | P2 | Observabilidad fragmentada | Panel AC (lectura) |
| AC-F08 | P2 | min_hold meta≠código | Disclaimer (no “arreglar” freeze) |
| AC-F09 | P2 | +90.75 no validado OOS nuevo | No PAPER |
| AC-F10 | P3 | Red local / token (fortaleza) | Mantener |

Detalle completo en `backend/app/research/etapa_ac/findings.py`.
