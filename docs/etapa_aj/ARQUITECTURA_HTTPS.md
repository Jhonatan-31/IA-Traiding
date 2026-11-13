# AJ1 — Arquitectura HTTPS privada (propuesta)

## Ruta objetivo

```
Dispositivo autorizado (tailnet)
  → HTTPS https://servidor-ebz.tail528f82.ts.net:10000
  → Tailscale Serve (terminación TLS, SOLO tailnet)
  → http://127.0.0.1:8090 (nginx dashboard)
  → /api/* → api:8000
  → /ws/*  → market-stream:8000
```

## Por qué puerto 10000

- 443 ya usa **Funnel** → EVS (`3080`). No reutilizar.  
- 8443 ya sirve Consultate. No reutilizar.  
- 10000 está en la lista de puertos funnel del nodo, pero **Serve sin Funnel** lo deja privado en la tailnet.  
- Tras activar Serve, verificar `tailscale funnel status` y confirmar que **10000 no aparece como Funnel**.

## Cookies Secure

Serve termina TLS; el hop local a nginx es HTTP. La API ya marca `Secure` si `X-Forwarded-Proto: https` (AH). Validar en pruebas que el header llega; si no, documentar ajuste nginx (sin aplicar ahora).

## Mutaciones / CSRF

- Lectura: cookie `ib_read_session` (HttpOnly, SameSite=Lax).  
- Control: `X-Lab-Token` (no cookie) — CSRF de mutaciones no depende de cookie de lectura.

## Funnel

**Prohibido** para Trading Bot. Comando a evitar: `tailscale funnel … 8090`.

## CT / nombre

El hostname MagicDNS ya puede ser público por Funnel EVS. No introducir nombres sensibles adicionales.
