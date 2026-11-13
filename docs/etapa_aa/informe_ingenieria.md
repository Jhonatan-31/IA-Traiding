# Etapa AA — Entrega de ingeniería

## Módulos

- `backend/app/research/etapa_aa/` — freeze, ingest, synthetic, evaluate, stats, adversarial, run_aa, center_aa
- API: `/api/research/center?run_etapa_aa=true`, `/api/research/etapa-aa`
- UI: sección **Validación independiente** en `ResearchCenterPage.tsx`
- Tests: `backend/tests/test_etapa_aa.py`

## Entregables docs

- AA0 manifiesto, AA1 prerregistro
- Informes ejecutivo / cuantitativo / técnico / seguridad
- Auditoría adversarial, pruebas, rollback

## Tags / commits

- Base: `614bb9d` / `checkpoint-etapa-z`
- Pre: `checkpoint-etapa-aa-pre-20261113_095420`
- Post: `checkpoint-etapa-aa` (al commit de cierre)

## Veredicto embebido

`INCONCLUSA` — activate=false, authorize_paper_trial=false.
