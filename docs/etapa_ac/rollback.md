# Rollback AC

```bash
git checkout checkpoint-etapa-ac-pre-20261113_104819
# o
git checkout checkpoint-etapa-ab
```

```bash
docker compose exec -T db pg_restore -U paper -d paper --clean --if-exists < backups/paper_pre_etapa_ac_20261113_104819.dump
```

No `docker compose down -v`.
