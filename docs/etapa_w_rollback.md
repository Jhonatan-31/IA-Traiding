# Etapa W — Rollback

## Código

```bash
git checkout checkpoint-etapa-w-pre-20261110_115036
# o el tag de cierre checkpoint-etapa-w
docker compose up -d --build
```

## Datos paper

```bash
docker compose exec -T db pg_restore --clean --if-exists -U paper -d paper < backups/paper_pre_etapa_w_20261110_115036.dump
```

## Historial de mercado

El directorio `data/market_history` es independiente de los ledgers.  
Para liberar disco: borrar `data/market_history/raw` y/o `parquet` (re-descargable).
