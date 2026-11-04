# Etapa T — Diagnóstico de baja frecuencia (Demo)

**Checkpoint:** `checkpoint-etapa-t-pre-20261104_115942`  
**Backup:** `backups/paper_pre_etapa_t_20261104_115942.dump`  
**Fecha auditoría:** 2026-11-04 ~17:00 UTC  
**Política Demo (A / baseline):** `demo_policy_v1_20261103` — **sin alterar**

## Estado operativo

| Campo | Valor |
|---|---|
| Bot Demo | RUNNING |
| Ciclos | 164 |
| Eval configurada | `DEMO_EVERY_SECONDS=60` |
| Cadencia reciente (logs) | ~62 s/ciclo |
| Cadencia media histórica | ~350 s (incluye periodos STOPPED / huecos) |
| Símbolos | BTCUSDT, ETHUSDT, SOLUSDT |

## Decisiones (n=508)

| Acción | n | % |
|---|---:|---:|
| HOLD | 474 | 93.31% |
| BUY | 18 | 3.54% |
| SELL | 16 | 3.15% |

### Motivos (top)

| Motivo | Acción | n | Interpretación |
|---|---|---:|---|
| `hold_position` | HOLD | 393 | Ya hay posición: no se evalúa entrada en ese símbolo |
| `flags_3_of_5_insufficient` | HOLD | 49 | Casi señal (3/5); falta 1 condición para BUY 4/5 |
| `bot_stopped_entries_blocked` | HOLD | 24 | Usuario/sistema con entradas bloqueadas |
| `policy_4_of_5_flags` | BUY | 17 | Entrada válida política v1 |
| `trend_break_1m` | SELL | 10 | Salida por ruptura de tendencia |
| `flags_2_of_5_insufficient` | HOLD | 8 | Señal débil |
| `take_profit_2pct` | SELL | 5 | Objetivo +2% |
| `stop_loss_1pct` | SELL | 1 | Protección −1% |
| `policy_5_of_5_flags` | BUY | 1 | Las 5 condiciones |

**HOLD de entrada** (excluyendo protecciones / hold_position): 81 decisiones.  
De ellas, **57** son insuficiencia de flags (70%) y **24** bot detenido.

## Condiciones fallidas (entre HOLD por flags, n=58)

| Condición | % fallida | Lectura |
|---|---:|---|
| `vol_ok` (vol > SMA20) | **89.7%** | Principal cuello de botella |
| `trend_1m` (EMA9>EMA21 1m) | **81.0%** | Segundo cuello |
| `trend_5m` | 24.1% | Suele estar OK |
| `rsi_ok` | 19.0% | Suele estar OK |
| `atr_ok` | **0%** | Casi nunca bloquea |

Conclusión: la política 4/5 no “falla” por falta de ciclos; falla porque **volumen relativo + tendencia 1m** rara vez coinciden juntos con el resto. No se deben bajar umbrales solo para fabricar compras.

## Operaciones DEMO ejecutadas

| Side | n | Nocional | Fees | rPnL |
|---|---:|---:|---:|---:|
| BUY | 18 | 447.49 | 0.4475 | 0 |
| SELL | 16 | 398.84 | 0.3988 | +0.6837 |

Posiciones abiertas al cierre de auditoría: ETHUSDT, SOLUSDT.  
Cash ≈ 950.51 USDT · peak_equity ≈ 1002.55 · initial 1000.

## Shadow / IA

| Métrica | Valor |
|---|---|
| Predicciones | 264 RESOLVED (0 PENDING en tabla) |
| Fuentes | 24 live + 240 replay |
| Hits / misses (retorno observado) | 133 / 131 |
| `calibrated_probability` | **NULL** (sin calibración persistida) |
| Suficiencia para ejecución | **NO** → Estrategia C = observación |

## Aislamiento de carteras (OK)

Ledgers distintos: `demo_manual_control`, `lab_auto`, `express_test_20261103`, `research_sim`, SMA paper (`virt_*` / account). Sin mezcla de saldos.

## Implicación para Etapa T

1. **Estrategia A** = Demo 4/5 congelada (referencia).  
2. **Estrategia B** debe usar **reglas estructurales distintas** (p. ej. cruce EMA + filtro de costos), no “3 de 5”.  
3. **Estrategia C** permanece en observación hasta calibración y evidencia prospectiva.
