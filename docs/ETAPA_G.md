# Etapa G — Investigación cuantitativa y backtest de cartera

## Verificación previa

| Item | Valor |
|------|-------|
| Base | `48453d5` / `checkpoint-etapa-f` |
| Checkpoint | `checkpoint-pre-etapa-g` |
| Backup | `backups/paper_pre_etapa_g_*.sql` |
| Paper | cash 875 · 5 pos · 5 trades · Shadow AI · PAPER_AI off |

## G.1 Auditoría

Ver `docs/ETAPA_G_METRICS_AUDIT.md`.

- `net_return_sum` Etapa F = **Σ fracciones por trade**, no equity de cartera.
- Shadow `mean_net_return` incluye HOLD hipotéticos ≠ PnL ejecutable.
- CI i.i.d. sobreestima precisión; G usa block bootstrap + holdout de cartera.
- Ejecución G: señal en close t → fill en **open t+1**.

## Dataset

- 15 símbolos · **22 500** velas 1h (incremental, 0 gaps/dupes estimados).
- Job: `docker compose --profile ml run --rm ml-research`

## Resultado holdout (capital 1000, costos 0.1%+0.1%)

Ninguna estrategia con `robust_edge` (retorno > 0 y IC bloques low > 0).
Mejor en selección: **cash**. PAPER_AI **no** autorizado.

## Rollback

```powershell
git checkout checkpoint-pre-etapa-g
docker compose up -d --build
# nunca down -v
```
