# INFORME — Activación Fase B (HTTPS privado)

**Fecha intento:** 2026-11-13 ~16:36–16:40 America/Bogota  
**Autorización:** solo Fase B · **no** C · **no** D

## VEREDICTO

**FASE B BLOQUEADA POR PREFLIGHT**

Seguimiento: incidente **EBZ-CONNECT-01** → `INFORME_EBZ_CONNECT_01.md` (intervención física requerida; acceso remoto no recuperado).

No se ejecutó `tailscale serve --https=10000` ni ningún otro cambio en EBZ.

### Causa

Imposible completar el preflight obligatorio: **sin acceso SSH administrativo al host EBZ** desde la estación de trabajo.

| Prueba | Resultado |
|--------|-----------|
| `ssh consultate` (LAN `192.168.1.12:22`) | Timeout |
| Ping `192.168.1.12` | 100% pérdida |
| Tailscale `servidor-ebz` `100.107.168.61` | `active; relay "mia"` pero **rx=0** |
| `tailscale ping 100.107.168.61` | no reply / timeout |
| SSH `adminebz@100.107.168.61:22` | Connection timed out |
| SSH MagicDNS `servidor-ebz.tail528f82.ts.net` | (reintento) |

Sin SSH no se puede: correr `aj_activation_preflight.sh`, snapshot Serve/Funnel, activar Serve, ni rollback seguro.

## Referencias git (estación local)

| Ítem | Valor |
|------|--------|
| `HEAD` / tag `checkpoint-etapa-aj` | `6def1c9` |
| Deploy EBZ (última evidencia AJ) | `9e50776` / luego redeploy docs — **no revalidado hoy** por falta de acceso |

## HTTPS

| Campo | Estado |
|-------|--------|
| URL privada | `https://servidor-ebz.tail528f82.ts.net:10000` — **no activada** |
| Puerto 10000 | **no configurado** (comando no ejecutado) |
| Certificado | N/A |
| WebSocket vía Serve | N/A |
| Segundo dispositivo | N/A |
| Acceso fuera de tailnet | N/A |

## SERVICIOS AJENOS

Sin cambios (ningún comando Tailscale/Docker ejecutado en EBZ en este intento).

- EVS Funnel 443→3080: **no tocado**
- Consultate Serve 8443→8088: **no tocado**

## SEGURIDAD (estado conocido previo; no reconfirmado live)

| Control | Estado esperado / nota |
|---------|------------------------|
| Auth lectura | Debe permanecer OFF — no se tocó |
| LAN 8090 | Debe permanecer — no se tocó |
| Funnel Trading | No creado |
| WAN Trading | No expuesto |
| A/B, PAPER | No reconfirmados hoy |

### Hallazgo de cola (informativo; no es el bloqueo)

La tailnet visible desde el laptop incluye dispositivos de **varios usuarios** (`jhonatanalexisr405@`, `michaellozadablanco32@`, `jhorjanperdomo1@`). Con ACLs permisivas, Serve `:10000` sería alcanzable por peers de la tailnet (igual que hoy `:8090` por IP Tailscale). No se llegó a evaluar ACL live por falta de SSH. Al reintentar Fase B, conviene revisar ACL antes/después si se desea restringir a nodos de confianza.

## PRÓXIMO PASO

1. Restaurar conectividad a EBZ (LAN y/o Tailscale con `rx>0` / `tailscale ping` OK).  
2. Reejecutar autorización Fase B (mismo alcance).  
3. Preflight → snapshot Serve/Funnel → `sudo tailscale serve --bg --https=10000 http://127.0.0.1:8090` → pruebas.  
4. **No** Fase C/D hasta nueva orden.

Fase C **no** está lista de solicitud operativa hasta que B quede verificada.
