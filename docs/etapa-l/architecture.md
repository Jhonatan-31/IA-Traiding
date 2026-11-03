# Etapa L — Arquitectura trade-executor (PAPER_ONLY)

```
┌─────────────┐     klines públicas      ┌──────────────────┐
│ Binance     │ ───────────────────────► │ trade-executor   │
│ Vision API  │                          │ (lab.runner)     │
└─────────────┘                          └────────┬─────────┘
                                                  │
                    SMA10/50 señal autorizada     │
                                                  ▼
                                         ┌────────────────┐
                                         │ lab_signals    │
                                         │ lab_orders     │◄── cola PG (NEW→VALIDATED→FILLED/REJECTED)
                                         └────────┬───────┘
                                                  │ risk gates + CB lab
                                                  ▼
                                         ┌────────────────┐
                                         │ lab_accounts   │  cash 1000 lab_auto
                                         │ lab_positions  │  ≠ account (SMA 875)
                                         │ lab_trades     │  ≠ virt research_sim
                                         └────────────────┘

worker SMA ──► account / positions / trades   (histórico, intacto)
shadow-scheduler ──► prospect_* / virt_*      (solo investigación)
IA Shadow ──► NO ejecuta en lab
```

Controles: pause `lab_executor_state`, circuit breaker lab, token `X-Lab-Token`, sin API keys.
