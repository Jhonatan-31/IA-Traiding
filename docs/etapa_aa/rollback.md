# Etapa AA — Rollback

## Checkpoint previo

```bash
git checkout checkpoint-etapa-aa-pre-20261113_095420
# o
git checkout checkpoint-etapa-z   # 614bb9d
```

## Restore DB (si hiciera falta)

```bash
docker compose exec -T db pg_restore -U paper -d paper --clean --if-exists < backups/paper_pre_etapa_aa_20261113.dump
```

## Datos AA (opcional retirar particiones nuevas)

Particiones 1d `year=2025/month=11+` y `year=2026` bajo `data/market_history/parquet/` y zips en `raw/`. No borrar volúmenes Docker con `down -v`.

## Post-cierre

Tag: `checkpoint-etapa-aa`  
Backup post: `backups/paper_post_etapa_aa_*.dump`
