# Etapa H — Validación prospectiva

## Auditoría

| Check | Resultado |
|-------|-----------|
| Base | `4449180` / `checkpoint-etapa-g` |
| Checkpoint | `checkpoint-pre-etapa-h` |
| Backup | `backups/paper_pre_etapa_h_*.sql` |
| Paper SMA | cash 875 · 5 pos · 5 trades |
| Shadow AI | activo · PAPER_AI false |
| Órdenes reales | no hay endpoints firmados ni API keys |

## Arquitectura

```
Protocolo pre-registrado
    → prospect_experiments (BACKTEST | SHADOW_REPLAY | SHADOW_LIVE | PAPER_TRADE)
    → prospect_decisions (inmutables)
    → job resolve → prospect_outcomes
virt_* ledger  ≠  account/positions/trades (SMA paper)
```

## API

- `GET /api/prospect/status`
- `GET /api/prospect/decisions` (filtros)
- `GET /api/prospect/protocols`
- `GET /api/prospect/ledger`
- `GET /api/prospect/benchmarks`
- `POST /api/prospect/shadow-live/run`
- `POST /api/prospect/resolve`

## Regla

Resultado negativo válido. Sin PAPER_AI. Sin trading real.
