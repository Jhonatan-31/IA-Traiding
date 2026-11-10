# Etapa X — Rollback

```bash
git checkout checkpoint-etapa-x-pre-20261110_144121
docker compose up -d --build
docker compose exec -T db pg_restore --clean --if-exists -U paper -d paper < backups/paper_pre_etapa_x_20261110_144121.dump
```

Historial Parquet en `data/market_history` no se altera por el rollback de código.
