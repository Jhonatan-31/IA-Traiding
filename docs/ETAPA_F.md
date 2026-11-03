# Etapa F — Validación, calibración, resolución Shadow y circuit breaker

## Auditoría inicial (F.1)

| Check | Valor |
|-------|-------|
| Commit base | `57ce025` / `checkpoint-etapa-e` |
| Checkpoint pre-F | `checkpoint-pre-etapa-f` |
| Backup | `backups/paper_pre_etapa_f_*.sql` |
| Modo | PAPER_ONLY + SHADOW_AI |
| Capital | cash 875 · 5 pos · 5 trades SMA |
| PAPER_AI | no |

## Datos

- 15 símbolos Spot · intervalo 1h · **18 000** velas cerradas · **17 175** muestras etiquetadas
- Calidad: 0 gaps estimados, 0 duplicados (run incremental)
- Modelo activo: `v20261103T193950Z` (HGB)

## Conclusión económica

**Ninguna estrategia muestra edge robusto** (`robust_edge=false`: requiere media neta > 0 y IC95 inferior > 0).
Cash es la mejor opción neta en el período de modelado. HGB calibrado reduce pérdidas vs HGB crudo pero sigue ≤ 0 en el IC.

## Rollback

```powershell
git checkout checkpoint-pre-etapa-f
docker compose up -d --build
# Nunca down -v
```
