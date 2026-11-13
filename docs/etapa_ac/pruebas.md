# Pruebas AC

```text
pytest tests/test_etapa_ac.py tests/test_etapa_ab.py tests/test_etapa_aa.py \
  tests/test_demo_stop_protections.py tests/test_market_stream.py -q
27 passed
```

| Suite | Resultado |
|---|---|
| AC (reconcile, Vision drop, prospect off) | PASS |
| AB/AA regresión | PASS |
| demo stop protections | PASS |
| market_stream | PASS |

No ejecutadas en esta pasada: adversarial WS live disconnect e2e, kill-DB mid-fill (riesgo alto) — documentadas como NOT TESTED / futuras.
