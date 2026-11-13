# AI5 — Reconciliación 63 vs 69 tablas

## Hallazgo

| Fuente | Tablas públicas | Entorno |
|--------|-----------------|----------|
| EBZ paper productivo (2026-11-13) | **63** | `/srv/apps/ia-bot-trading` Docker |
| Dump HITACHI `paper_ebz_20261113_195855` TOC DATA | **63** (mismas tablas) | Mismo ledger EBZ |
| Restore aislado AH | **63** · demo/active STOPPED | Contenedor efímero |
| Restore aislado AE | **69** | Dump **local** pre-AE (`paper_pre_etapa_ae_*`, ~1 MB) |

## Conclusión

**No es pérdida de tablas en EBZ.**  
AE restauró un dump del histórico local (más objetos de investigación/lab antiguos).  
EBZ nació con paper limpio y acumula 63 relaciones públicas actuales.

Verificación: listado `pg_tables` prod ≡ nombres en `pg_restore -l` del dump HITACHI.

## Acción

Ninguna reconstrucción automática. No mutar productivo.
