# Etapa Z — Informe de ingeniería

## Arquitectura añadida

```
backend/app/research/etapa_z/
  audit_z0.py      # integridad datos/causalidad
  hypotheses.py    # fichas congeladas
  engine.py        # simulación long-only + costos
  adversarial.py   # revisión adversaria
  micro_diag.py    # Z4/Z5 sin cargas masivas
  run_z.py         # orquestación + persistencia
  center_z.py      # payload UI
```

API: `GET /api/research/etapa-z`, `center?run_etapa_z=true`  
UI: sección **Laboratorio de Estrategias Avanzadas**

## Pruebas

- `tests/test_etapa_z.py` — safety, freeze, agregación causal, adversarial
- Regresión: `test_etapa_y` / `test_etapa_x` no modificados en lógica

## Rendimiento

- Carga Parquet **1d/4h** preagregados (evita re-agregar 525k×3 desde 1m).
- Runtime lab ~1–2 min en contenedor API.

## Errores / hallazgos técnicos

1. Store Parquet **omite** `taker_buy_*` de Vision → bloquea OFI sin re-ingesta.
2. `docker cp` de carpeta anidó `etapa_z/etapa_z` — corregido copiando contenido.
3. Scripts `.sh` con CRLF fallan en contenedor Linux — usar `python -m`.

## Recursos

- Disco libre historial ~99 GB al inicio Z.
- No se descargaron aggTrades ni metrics OI masivos.

## Riesgos técnicos

- `list_partitions` hace rglob de meta en cada `load_range` (aceptable para 1d/4h).
- Resultados grandes JSON en `/artifacts/history` (bind mount).
