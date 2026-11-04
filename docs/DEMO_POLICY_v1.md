# Política DEMO Manual Control — v1 (congelada)

**Ledger:** `demo_manual_control` · **Capital inicial (una vez):** 1000 USDT  
**Control:** usuario INICIAR/DETENER · sin fecha de caducidad  
**Símbolos:** BTCUSDT, ETHUSDT, SOLUSDT  
**PAPER_ONLY** · no toca SMA / Lab / Shadow / Express  

## Entrada (más sensible que Express 5/5)

Indicadores en velas **cerradas** 1m y 5m:

1. `EMA9_5m > EMA21_5m`
2. `EMA9_1m > EMA21_1m`
3. `40 ≤ RSI14_1m ≤ 70`
4. `vol_1m > SMA(vol_1m, 20)`
5. `ATR14_1m/close ≤ 0.02`

**BUY** si al menos **4 de 5** condiciones son verdaderas **y** `signal_score ≥ 0.80`.  
**HOLD** si no. No forzar compras.

## Salida

Con inventario del símbolo:

- Stop-loss −1% desde entry (mark fresco / última 1m cerrada o ticker observado)
- Take-profit +2%
- Ruptura: `EMA9_1m < EMA21_1m` **y** `RSI14_1m < 42`

## Riesgo (v1, no optimizado)

- Máx 25 USDT por compra  
- Máx 3 posiciones  
- Exposición máx 75 USDT coste  
- Fee 10 bps · slip 5 bps  
- Pausa compras si equity ≤ peak × 0.97 (−3%)  
- Datos incompletos / stale → HOLD / rechazo  

## Control STOPPED

- Bloquea **nuevas entradas** en motor (no solo UI)  
- Cancela órdenes NEW/VALIDATED de BUY pendientes  
- **Mantiene** posiciones  
- **Permite** salidas protectoras (SL/TP/ruptura)  

## Versión

`demo_policy_v1_20261103` — cambios futuros requieren confirmación explícita y bump de versión.
