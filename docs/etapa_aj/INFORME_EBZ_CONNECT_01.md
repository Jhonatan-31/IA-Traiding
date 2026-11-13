# INFORME — Incidente EBZ-CONNECT-01

**Ventana:** 2026-11-13 ~16:36–16:50 America/Bogota  
**Alcance:** diagnóstico de conectividad · **sin** Serve Trading · **sin** auth · **sin** cambios en EBZ

---

## VEREDICTO

**INTERVENCIÓN FÍSICA REQUERIDA**  
(también: **ACCESO REMOTO NO RECUPERADO**)

No fue posible recuperar SSH ni ninguna ruta de datos hacia EBZ desde la estación.  
**No** se ejecutó ningún cambio en el servidor, Docker, Tailscale Serve/Funnel ni ACLs.

---

## CAUSA

### Hechos confirmados

1. **La estación no está en la LAN de EBZ (`192.168.1.0/24`).**  
   - Wi‑Fi activa: `192.168.31.197/24`, gateway `192.168.31.1` (ping gateway OK).  
   - Ethernet: `192.168.4.171/24`, gateway `192.168.4.90`.  
   - No hay interfaz en `192.168.1.x`. ARP sin entradas `192.168.1.12`.  
   - `Test-NetConnection` a `192.168.1.12` puertos 22/8090/3080/8088/443 → **Tcp=False**.  
   - `192.168.1.1` → inalcanzable.  
   → El fallo LAN desde esta estación es **falla de ruta/subred del cliente**, no prueba por sí sola que EBZ esté apagado.

2. **Tailscale del cliente funciona.**  
   - Cliente 1.104.4, UDP OK, IPv4 público visible, DERP Miami ~45 ms.  
   - Ping Tailscale a **creo-server** (`100.84.201.34`): **OK** (~4 ms, directo).  
   - Internet TCP a 8.8.8.8:53 y 1.1.1.1:443: **OK**.

3. **EBZ no responde en el plano de datos Tailscale.**  
   - `servidor-ebz` aparece `active; relay "mia"` con **rx=0** (solo TX local, sin RX).  
   - `tailscale ping 100.107.168.61`: timeout / no reply.  
   - `tailscale ping --tsmp`: también **no reply**.  
   - Según docs Tailscale: fallo TSMP ⇒ no hay camino de red entre nodos (no es solo ACL).  
   - TCP 22/8090/443 a IP Tailscale: **False**.

4. **Ruta pública Funnel (EVS) también falla.**  
   - `https://servidor-ebz.tail528f82.ts.net/` → timeout.  
   - `https://servidor-ebz.tail528f82.ts.net:8443/` → timeout.  
   → Independiente de estar o no en `192.168.1.0/24`: el nodo EBZ **no entrega** servicio vía Funnel/Serve desde Internet.

5. **MagicDNS OK.**  
   - `servidor-ebz` / `servidor-ebz.tail528f82.ts.net` → `100.107.168.61`.  
   → No es fallo DNS.

6. **Último acceso exitoso conocido (misma jornada).**  
   - ~15:46–15:56 America/Bogota: SSH `consultate` (LAN) y deploy OK.  
   - ~16:36+: LAN y Tailscale fallan.  
   → Cambio en ~40 min: red de la estación y/o estado de EBZ/uplink.

### Hipótesis (orden de probabilidad operativa)

| # | Hipótesis | Encaja con |
|---|-----------|------------|
| H1 | EBZ sin uplink a Internet / Tailscale path roto (cable, router WAN, `tailscaled`) | Funnel timeout + TSMP fail + rx=0 |
| H2 | EBZ apagado, colgado o reiniciando | Igual; “active” en mapa puede ser residual de coordinación |
| H3 | Estación cambió de red (ya no en `192.168.1.0/24`) | Explica LAN; **no** explica Funnel/TSMP solos |
| H4 | ACL bloquea | **Poco probable**: TSMP también falla (ACL suele permitir TSMP y bloquear ICMP) |

### Causa raíz

**No concluyente remota.**  
Evidencia suficiente para afirmar: **no hay camino de datos usable a EBZ** desde esta estación ni vía Funnel público.  
Se requiere **consola física / out-of-band** para discriminar H1 vs H2 (y confirmar si el host vive).

---

## RED

| Canal | Resultado |
|-------|-----------|
| LAN `192.168.1.12` | Inalcanzable (estación fuera de subred) |
| SSH LAN :22 | Tcp=False |
| Trading :8090 LAN | Tcp=False |
| Tailscale IP | DNS OK; ping/TSMP/TCP fallan |
| MagicDNS | Resuelve; sin conectividad |
| Funnel EVS :443 | Timeout |
| Serve Consultate :8443 | Timeout |
| Peer control `creo-server` | Tailscale ping OK |
| Gateway Wi‑Fi | OK |
| Internet estación | OK |

**Clasificación (§6):** **D — Fallan todas las rutas hacia EBZ** (desde esta estación + Funnel público).  
Segundo dispositivo con SSH a EBZ: **no disponible** → evidencia de peer solo vía Funnel/Internet.

---

## INFRAESTRUCTURA

| Componente | Estado |
|------------|--------|
| Docker / API / runners / AF / backups live | **NO VERIFICABLE** (sin SSH) |
| Último backup conocido (AJ) | `paper_ebz_20261113_205653` (antes del incidente de acceso) |
| Cron 2026-11-14 00:00 Bogota | **PENDIENTE**; si EBZ sigue caído a esa hora → brecha de cobertura |

No se reinició Docker ni se inventó estado financiero.

---

## SEGURIDAD

| Control | Estado |
|---------|--------|
| A/B STOPPED | **NO VERIFICABLE** en vivo |
| PAPER_ONLY | **NO VERIFICABLE** en vivo |
| D28H5 / Prospect | Sin evidencia de cambio remoto (ningún comando aplicado) |
| Consultate / EVS | Endpoints conocidos **no responden** desde aquí |
| Serve Trading :10000 | **No activado** (nunca se ejecutó) |
| Auth lectura | No tocada |

### Tailnet / política (antes de reintentar Serve)

Dispositivos visibles incluyen usuarios distintos (`jhonatanalexisr405@`, `michaellozadablanco32@`, `jhorjanperdomo1@`).  
Sin acceso a la consola admin, **no** se leyó el policy file.  
Riesgo: política por defecto “allow all” ⇒ Serve `:10000` con auth OFF expondría el dashboard a **todos** los peers de la tailnet (igual que hoy `:8090` por IP Tailscale, cuando EBZ está up).  
**No** se modificaron ACLs (requiere autorización).

---

## FASE B

**BLOCKED_BY_CONNECTIVITY**

Condiciones secundarias al recuperar acceso:

- Revisar ACL/grants → posible **BLOCKED_BY_ACCESS_POLICY** si el acceso residual a peers no confiables es inaceptable con auth OFF.
- Postflight salud servicios → posible **BLOCKED_BY_SERVICE_HEALTH**.

**No** READY_TO_RETRY.  
**No** Fase C/D.

---

## ENTREGA / EVIDENCIA

- Script: `docs/etapa_aj/_ebz_connect01_station.ps1`
- Log: `docs/etapa_aj/_evidence_ebz_connect01/station_20261113_164323.txt`
- Cambios en EBZ: **ninguno**
- Serve/Funnel ajenos: **no modificados**

### Guía física para el usuario (obligatoria)

1. Comprobar alimentación e indicadores de encendido de EBZ.  
2. Verificar cable Ethernet y puerto del switch/router; LEDs de enlace.  
3. En el router: ¿aparece el host? ¿sigue en `192.168.1.12` u otra IP?  
4. Si hay monitor/teclado: consola local **sin reiniciar de inmediato**.  
5. En consola, si hay login, recopilar (no pegar secretos):  
   `uptime; ip -br addr; ip route; systemctl is-active ssh tailscaled docker; tailscale status; free -h; df -h`  
6. Anotar hora de último reinicio y si Internet sale (`ping 1.1.1.1` / `tailscale netcheck`).  
7. **Reinicio forzado:** solo con autorización explícita; último recurso (riesgo de escrituras a medias).

### Próxima acción concreta

1. Intervención física / consola → restablecer uplink + SSH.  
2. Desde estación: idealmente conectarse a Wi‑Fi/LAN `192.168.1.0/24` **o** confirmar Tailscale ping/TSMP a EBZ.  
3. Postflight trading (salud, A/B STOPPED, backups) **antes** de reautorizar Fase B.  
4. Revisar ACL Tailscale (Preview rules) **antes** de Serve `:10000` con auth OFF.
