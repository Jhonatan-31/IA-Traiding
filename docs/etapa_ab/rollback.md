# Rollback Etapa AB

```bash
git checkout checkpoint-etapa-ab-pre-20261113_101528
# o
git checkout checkpoint-etapa-aa
```

```bash
docker compose exec -T db pg_restore -U paper -d paper --clean --if-exists < backups/paper_pre_etapa_ab_20261113_101528.dump
```

No usar `docker compose down -v`.
