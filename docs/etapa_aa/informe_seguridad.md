# Etapa AA — Informe de seguridad

## Estados operativos (verificados post-AA)

| Control | Estado |
|---|---|
| A Conservadora (`demo_state`) | STOPPED |
| B Trading Activo (`active_state`) | STOPPED (`paper_only: true`) |
| Express | ENDED (deadline previo) |
| PAPER_ONLY | activo |
| PAPER_AI / Shadow AI | no ejecutando órdenes |
| Órdenes reales | ninguna |
| Nuevos runners | no creados |
| `docker compose down -v` | no usado |

## Integridad

- Ledgers/posiciones/órdenes: no modificados por AA
- Datos históricos originales Z preservados; AA añadió particiones 1d post-2025-10
- Secretos: no expuestos en docs

## Docker

Servicios operativos (api, db, dashboard, runners existentes sin cambios de lógica de trading).

## Backups

- Pre: tag `checkpoint-etapa-aa-pre-20261113_095420`, dump `backups/paper_pre_etapa_aa_20261113.dump`
- Post: ver `rollback.md` / tag `checkpoint-etapa-aa`
