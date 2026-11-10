# Rollback Etapa Y

## Checkpoint

- Pre: `checkpoint-etapa-y-pre-20261110_150623`
- Post (tras commit): `checkpoint-etapa-y`

## Restaurar código

```bash
git checkout checkpoint-etapa-x
# o
git checkout checkpoint-etapa-y-pre-20261110_150623
```

## Notas

- Etapa Y solo añade investigación (salidas Y0–Y4), API/UI y docs/tests.
- No modifica carteras ni reactiva A/B.
- Datos Parquet en `data/market_history` no se revierten con git; el backup previo de etapa Y los conserva si se creó bajo `backups/`.
