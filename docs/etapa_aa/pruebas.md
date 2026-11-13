# Etapa AA — Pruebas

Ejecutado en contenedor `api`:

```text
pytest tests/test_etapa_aa.py tests/test_etapa_z.py tests/test_etapa_y.py -q
................  16 passed in 0.11s
```

## Cobertura AA (`test_etapa_aa.py`)

| Test | Resultado |
|---|---|
| safety flags PAPER_ONLY / ACTIVATE_FORBIDDEN | PASS |
| freeze hash `5326edb8a539cfe5` | PASS |
| suite sintética motor | PASS |
| bootstrap muestra corta | PASS |
| decide → RECHAZADA si exceso ≤0 | PASS |
| adversarial bloquea sin exceso | PASS |

## Regresiones

- `test_etapa_z.py`: PASS
- `test_etapa_y.py`: PASS

## Omitidas

- Tests de ingesta de red en CI (requieren Vision); ingesta verificada en ejecución AA (36/36 meses 1d).
- Tests E2E UI dashboard (rebuild manual).
