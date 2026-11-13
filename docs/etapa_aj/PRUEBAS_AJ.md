# AJ3 — Matriz de pruebas (aisladas + evidencia)

**Entorno de prueba:** TestClient FastAPI + assertions de docs/scripts (`backend/tests/test_etapa_aj.py`).  
**Sin** credenciales reales, **sin** órdenes, **sin** tocar carteras productivas.

| # | Caso | Resultado | Evidencia |
|---|------|-----------|-----------|
| 1 | Sin sesión → API privada rechazada | PASS | `test_aj1_no_session_rejected` |
| 2 | Usuario autorizado (header) | PASS | `test_aj2_authorized_header_ok` |
| 3 | Sesión válida (cookie post-login) | PASS | `test_aj3_valid_session_cookie` |
| 4 | Sesión inválida rechazada | PASS | `test_aj4_invalid_session_rejected` |
| 5 | Sesión expirada | OMITIDA | Requiere clock/max_age e2e; documentado `DASHBOARD_READ_SESSION_SECONDS` |
| 6 | Cookie modificada rechazada | PASS | `test_aj5_tampered_cookie_rejected` |
| 7 | Cookie Secure con HTTPS/`X-Forwarded-Proto` | PASS | `test_aj6_secure_cookie_with_forwarded_proto` |
| 8 | Credenciales no en logs | PASS | `record_denial` solo path/reason (AH/AI + código) |
| 9 | Token lectura ≠ mutaciones | PASS | `test_aj7_read_token_cannot_mutate` |
| 10 | Controles admin (`X-Lab-Token`) | PASS | mismo test (403 sin lab; 200 con lab) |
| 11 | WebSocket mercado público | PASS | `test_aj8` + `websocket_policy` |
| 12 | Datos privados no en rutas públicas | PASS | health/public libres; system gated |
| 13 | Bypass puerto backend | DISEÑO | `RUTAS_ALTERNATIVAS.md` — bind loopback **no aplicado** |
| 14 | Dashboard escritorio | OMITIDA | Requiere Serve HTTPS prod (Fase B) |
| 15 | Dashboard móvil | OMITIDA | Idem Fase B/C |
| 16 | Recuperación de acceso | PASS | logout + auth OFF preserva datos (`test_aj9`) |
| 17 | Desactivar auth sin perder datos | PASS | `test_aj9_auth_off_preserves_access_and_data_shape` |
| 18 | Healthchecks | PASS | `/api/health` + `/api/public/health` con auth ON |
| 19 | No alterar carteras | PASS | tests sin DB productiva; mutación simulada `started=False` |

**Regresión:** AJ+AI+AH+AG+AF → **46 passed** (2026-11-13).

**Prod (solo lectura):** auth OFF; A/B STOPPED; Serve Trading **no** activado.
