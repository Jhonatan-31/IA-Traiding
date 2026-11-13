# AE0 — Mapa real de infraestructura EBZ

**Fecha sonda:** 2026-11-13  
**Host:** `ebz` (Ubuntu 26.04 LTS nativo — **no** es WSL2/Windows)  
**Acceso:** SSH `consultate` → `adminebz@192.168.1.12` (+ Tailscale `100.107.168.61`)

```
HOST (Ubuntu 26.04, 14Gi RAM, 12 CPU, 344G disco ~11%)
  Docker Engine 29.9.2 + Compose v5.6.1
  ├── consultate_*          (NO TOCAR)
  ├── evs-bienestar-pastoral (NO TOCAR)
  └── ia-bot-trading        (este stack)
        red: ia-bot-trading_default
        vols: ia-bot-trading_paper_data, ia-bot-trading_ml_artifacts
        puerto host: 0.0.0.0:8090 → dashboard:8080
        Postgres: SOLO red interna (sin publish)
        restart: unless-stopped (todos)
        health Docker inicial: solo db=healthy; api/ms/dashboard añadidos en AE
```

## Puntos únicos de fallo

1. Host EBZ apagado / sin red → no hay watchdog externo configurado.
2. Disco lleno → Postgres/volumen.
3. Binance público caído → market + marcas.
4. Un solo nodo Docker (sin HA).
5. Dashboard LAN `:8090` sin auth de lectura.

## Diferencias vs Windows/WSL2 local

- EBZ = Linux nativo.
- Huecos “suspend Windows” no aplican igual; clasificar reinicio host/Docker/proceso/red/indeterminado.
- Ledger EBZ es **PAPER limpio** (independiente del dump local histórico).
