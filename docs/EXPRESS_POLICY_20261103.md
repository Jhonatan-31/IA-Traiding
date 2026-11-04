# Política Express Test — congelada ANTES del primer ciclo

**Cuenta:** `express_test_20261103` · **Capital:** 100 USDT virtuales  
**Símbolos:** BTCUSDT, ETHUSDT, SOLUSDT  
**Fin absoluto:** 2026-11-04 01:00:00 UTC (20:00 America/Bogota, 3-nov-2026)  
**Modo:** PAPER_ONLY · sin claves · sin PAPER_AI · sin tocar SMA/Lab/Shadow ledgers  

Checkpoint previo: git `112ecc7` + dump `backups/paper_pre_express_*.dump`.

## Evaluación

- Cada **60 s**.
- Indicadores solo sobre velas **cerradas** 1m y 5m (Binance public).
- Decisiones **sin** precios futuros.
- Si datos stale (>90 s sin precio usable) o indicadores incompletos → **HOLD** / rechazo.

## Umbrales (deterministas; no se retocan con resultados de esta prueba)

| Señal | Condición |
|-------|-----------|
| Tendencia 5m | `EMA9_5m > EMA21_5m` |
| Tendencia 1m | `EMA9_1m > EMA21_1m` |
| Momentum | `45 ≤ RSI14_1m ≤ 68` |
| Volumen | `vol_1m > SMA(vol_1m, 20)` |
| Volatilidad | `ATR14_1m / close ≤ 0.015` (1.5%) |

**Score** (0–1): promedio de las 5 condiciones booleanas (cada una 0/1).  
**BUY** solo si `score ≥ 0.80` **y** las 5 condiciones verdaderas (abstención si alguna falla).  
**SELL** (solo con inventario del símbolo):
1. Stop-loss: mark ≤ entry × (1 − 0.01)
2. Take-profit: mark ≥ entry × (1 + 0.02)
3. Ruptura: `EMA9_1m < EMA21_1m` **y** `RSI14_1m < 45`

**HOLD** en cualquier otro caso (incl. score intermedio).

## Riesgo / tamaño

- Máx **10 USDT** por compra.
- Máx **2** posiciones simultáneas.
- Exposición total máx **20 USDT** (coste).
- Sin apalancamiento / cortos / compras duplicadas del mismo símbolo.
- Pausa compras si equity ≤ peak × **0.98**.
- Tras `END_UTC`: **cero** nuevas compras/decisiones experimentales.
- Fin de prueba: **no** liquidación automática; informe de liquidación *hipotética* al último mark (costos estimados). Identificador si se añadiera cierre: `scheduled_test_end` (no usado en esta corrida salvo regla explícita futura).

## Costos de simulación

- Fee: **10 bps** (0.001) por lado.
- Slip base: **5 bps** (0.0005) adverso.
- Fill: `estimate_fill_price` / modelo local equivalente; rechazo si filtros LOT_SIZE / MIN_NOTIONAL fallan.

## Probabilidad

- `probability_validated=false` (no hay modelo calibrado validado para este express).
- `signal_score` ≠ probabilidad.

## Justificación breve

Umbrales conservadores para prueba funcional corta: exige alineación tendencia multi-TF + momentum no extremo + volumen + volatilidad acotada, priorizando abstención frente a fills forzados.
