# Informe final — Express Test `express_test_20261103`

Cierre: **2026-11-04 01:00:07 UTC** (20:00:07 America/Bogota) · `end_reason=absolute_deadline`  
Política congelada: `docs/EXPRESS_POLICY_20261103.md` · `express_v1_20261103_frozen`  
Checkpoint previo: git `112ecc7` + `backups/paper_pre_express_*.dump`

## Veredicto

Prueba **funcional** completada a tiempo. El bot **se abstuvo**: **0 compras, 0 ventas, 0 posiciones abiertas**.  
**No hay evidencia de ventaja económica.** No optimizar ni declarar edge.

---

## 1–15 Entregables

| # | Ítem | Resultado |
|---|------|-----------|
| 1 | Cobertura real | **00:17:47 → 01:00:07 UTC** (~42.3 min) · **42** ciclos · heartbeat OK |
| 2 | Decisiones | **BUY 0 · SELL 0 · HOLD 126** (42×3 símbolos) |
| 3 | Compras ejecutadas | **0** |
| 4 | Ventas ejecutadas | **0** |
| 5 | Operaciones cerradas | **0** |
| 6 | Todavía abiertas | **0** |
| 7 | Rentabilidad realizada | **0** |
| 8 | Rentabilidad no realizada | **0** |
| 9 | Neto est. post-costos | **100 USDT** (cash=100; liquidación hipotética N/A sin inventario) |
| 10 | Max drawdown | **0** (equity ticks min=max=100) |
| 11 | Aciertos/errores | **N/A** — sin trades cerrados |
| 12 | Prob. calibradas | `probability_validated=false` · score ≠ probabilidad |
| 13 | Limitaciones | ~42 min · 3 símbolos · política exigente (5/5 flags) · muestra no estadística |
| 14 | Integridad ledgers | Express aislado en 100. SMA 775 / research_sim 1000 intactos vs baseline. Lab auto operó por su propio executor (cash cambió de ~924.87→~973.62 por actividad Lab, **no** por Express). |
| 15 | Servicios | 7 originales **Up**; `express-runner` **Exited (0)** al deadline (correcto, `restart: no`) |

## Motivo de abstención

Razón dominante: `trend_not_aligned` (EMA9/21 1m o 5m).  
Scores observados 0.2–0.8; **BUY exige las 5 condiciones** → nunca se cumplió el paquete completo. Sin fills forzados. 0 rechazos de filtros (no hubo intentos de orden).

## Seguridad

PAPER_ONLY · sin claves · PAPER_AI off · sin cambio de SMA/umbrales globales · sin liquidación `scheduled_test_end` inventada · sin ops retroactivas tras 01:00.
