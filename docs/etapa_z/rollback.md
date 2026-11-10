# Rollback Etapa Z

```bash
git checkout checkpoint-etapa-y
# o
git checkout checkpoint-etapa-z-pre-20261110_164745
```

Restaurar DB si fuera necesario (Z no altera ledgers):

```bash
# solo si se sospecha corrupción ajena a Z
docker compose exec -T db pg_restore -U paper -d paper --clean --if-exists < backups/paper_pre_etapa_z_20261110_164745.dump
```

Resultados de investigación en `data/market_history/etapa_z_results*.json` son independientes del código.
