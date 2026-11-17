# AL9 — Red y continuidad EBZ

## Antecedente AK

`eno1` NO-CARRIER; operación vía Wi‑Fi (`wlp7s0`).

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
