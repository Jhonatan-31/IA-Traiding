# AL9 — Red y continuidad EBZ

## Antecedente AK

`eno1` NO-CARRIER; operación vía Wi‑Fi (`wlp7s0`).

## Lectura 2026-11-17 (post-deploy AL)

| Ítem | Estado |
|------|--------|
| eno1 | DOWN, NO-CARRIER (carrier=0) |
| wlp7s0 | UP, carrier=1, `192.168.1.12/24` |
| Gateway | `192.168.1.254` via wlp7s0 |
| market-stream / API | healthy; bookTicker público OK |
| Captura 24/7 | **no** iniciada (Wi‑Fi + sin autorización) |

## Política AL

- Verificar estado actual en despliegue (no asumir fallo persistente).
- No reiniciar red global, router, Tailscale ni firewall.
- Si conectividad insuficiente: V2 permanece aislado; captura permanente no se inicia.

## Checklist lectura segura

- `ip -br link` eno1 / wlp7s0
- Carrier / IP / gateway / DNS
- market-stream / PostgreSQL / sampler AF
- A/B STOPPED
- Backups recientes
- Consultate / EVS intactos
