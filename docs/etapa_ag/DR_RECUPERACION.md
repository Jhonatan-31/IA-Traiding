# AG5 — Recuperación ante desastres (AI Trading Bot Pro)

## Alcance

Recuperar el stack **paper** `ia-bot-trading` si EBZ deja de estar disponible.  
No cubre Consultate/EVS salvo mención de coexistencia.

## Qué restaurar (orden)

1. Código en commit conocido (`DEPLOY_GIT_COMMIT` / tag).
2. Compose + `.env` (secretos por canal seguro; **no** desde git).
3. Volumen/datos PostgreSQL `paper` desde dump `-Fc` + manifest/sha256.
4. Verificar A/B `STOPPED`, PAPER_ONLY, prospect disabled.
5. Levantar db → api → market-stream → runners → dashboard.
6. **No** iniciar compras; runners en STOPPED.
7. Validar `/api/public/health`, heartbeats, ledgers.

## Datos necesarios

- Dump `paper_ebz_YYYYMMDD_HHMMSS.dump` + `.sha256` + `.manifest.json`
- Commit git desplegable
- `LAB_CONTROL_TOKEN` (y futuro `DASHBOARD_READ_TOKEN`) vía canal seguro
- Inventario de puertos (8090)

## RPO / RTO (propuestos, no garantizados)

| Métrica | Propuesta | Evidencia |
|---------|-----------|-----------|
| RPO | ≤ 12 h | Cron 00:00/12:00 Bogota |
| RTO técnico stack | ≤ 4 h | Depende de host de reemplazo |
| RTO post-pérdida total | **No medido** | Requiere host + off-host real |

Restore aislado AE/AG mide tiempo de restore **local**, no el de reconstrucción completa tras pérdida del servidor.

## Prevención de compras duplicadas

- Confirmar `demo_state/active_state = STOPPED` antes de exponer UI.
- No auto-start runners en compose.
- Idempotencia de fills ya cubierta en etapas AD (persistente + LRU).

## Estado

Procedimiento **PREPARADO**. Restore aislado histórico: **VERIFICADO_EN_AE**. Off-host: **PREPARADO_SIN_ACTIVAR**.
