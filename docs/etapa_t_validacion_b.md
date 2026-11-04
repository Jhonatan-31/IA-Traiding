# Etapa T — Validación técnica Estrategia B

## Gates técnicos (no claim de rentabilidad)

| Gate | Estado |
|---|---|
| Política versionada y congelada | `active_policy_b_v1_20261104` |
| Ledger aislado | `active_exp_v1` (1000 USDT, no toca Demo/Lab/SMA/Express) |
| PAPER_ONLY | Sí |
| Backtest A vs B misma ventana | `docs/etapa_t_backtest_ab.json` (~720 barras 1m) |
| Tests unitarios señales | `tests/test_active_policy_b.py` — 5 passed |
| Idempotencia BUY por vela | UNIQUE (account, symbol, side, candle_1m_ms) |
| SL/TP/código de salida | Implementado |
| Cooldown / max entries hour | Implementado |
| INICIAR/DETENER independientes | `/api/active/b/start|stop` + token |
| Estrategia C ejecución | **Bloqueada** — IA NO VALIDADA |

## Resultado backtest (~12 h, 3 símbolos)

| | A Demo 4/5 | B Activo |
|---|---:|---:|
| Compras | 44 | 9 |
| Neto vs 1000 | ≈ −0.50 | ≈ −0.72 |

**No se declara ganadora.** Muestra insuficiente. B es más selectiva en esta ventana por filtro de costos vs ATR y estructura distinta; no se relajaron reglas para igualar el conteo de A.

## Autorización de ejecución virtual B

Autorizada solo en PAPER (`B_EXECUTION_AUTHORIZED=True`) tras gates de integridad.  
El runner `active-runner` arranca en **STOPPED**; el usuario debe INICIAR.

## Rollback

```bash
git checkout checkpoint-etapa-t-pre-20261104_115942
docker compose up -d --build
# opcional: restaurar dump backups/paper_pre_etapa_t_20261104_115942.dump
```
