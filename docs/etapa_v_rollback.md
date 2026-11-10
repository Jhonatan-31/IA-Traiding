# Etapa V — Rollback

## Código

```bash
git checkout checkpoint-etapa-v-pre-20261110_113700
# o, tras el tag de cierre:
# git checkout checkpoint-etapa-v
docker compose up -d --build
```

## Datos (Postgres paper)

```bash
# Detener writers si hace falta, luego:
docker compose exec -T db pg_restore --clean --if-exists -U postgres -d paper < backups/paper_pre_etapa_v_20261110_113700.dump
```

(Ajusta usuario/DB según `compose.yaml`.)

## Seguridad post-rollback

Verificar A/B `STOPPED`, PAPER_ONLY, sin órdenes nuevas en carteras operativas.
