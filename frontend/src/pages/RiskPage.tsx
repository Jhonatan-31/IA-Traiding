import { useEffect, useState } from "react";
import { api, fmtNum, fmtPct, type Overview, type RiskReport } from "../api";

export default function RiskPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [risk, setRisk] = useState<RiskReport | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    setError(null);
    let attempt = 0;
    while (attempt < 3) {
      const [oRes, rRes] = await Promise.allSettled([api.overview(), api.risk()]);
      if (oRes.status === "fulfilled") setOverview(oRes.value);
      if (rRes.status === "fulfilled") setRisk(rRes.value);
      if (oRes.status === "fulfilled" || rRes.status === "fulfilled") {
        setLoading(false);
        if (oRes.status === "rejected") setError(`overview: ${String(oRes.reason)}`);
        if (rRes.status === "rejected")
          setError((prev) => `${prev ?? ""} risk: ${String(rRes.reason)}`.trim());
        return;
      }
      attempt += 1;
      await new Promise((r) => setTimeout(r, 400 * 2 ** (attempt - 1)));
    }
    setLoading(false);
    setError("No se pudo cargar riesgo/overview tras reintentos");
  }

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(id);
  }, []);

  async function toggle() {
    if (!overview) return;
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      if (overview.engine?.paused) {
        await api.resume("dashboard_resume");
        setMsg("Simulación reanudada. Historial intacto.");
      } else {
        await api.pause("dashboard_pause");
        setMsg("Simulación pausada: sin nuevas entradas/salidas.");
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Gestión de riesgo</h2>
          <p>
            Separación explícita: ledger confirmado vs marcas observadas vs
            estimaciones de simulación.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void load()}>
            Actualizar
          </button>
          <button
            className={`btn ${overview?.engine?.paused ? "primary" : "danger"}`}
            disabled={busy || !overview}
            onClick={() => void toggle()}
          >
            {overview?.engine?.paused ? "REANUDAR SIMULACIÓN" : "PAUSAR SIMULACIÓN"}
          </button>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      {loading && !risk && <p className="muted">Cargando métricas de riesgo…</p>}
      {msg && (
        <div className="card" style={{ marginBottom: 14, borderColor: "#2dd4bf" }}>
          {msg}
        </div>
      )}

      <div className="grid stats" style={{ marginBottom: 14 }}>
        <div className="card">
          <div className="stat-label">Efectivo (ledger)</div>
          <div className="stat-value">{fmtNum(risk?.cash, 2)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">Exposición total (costo)</div>
          <div className="stat-value">{fmtNum(risk?.invested_cost, 2)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">Patrimonio mark-to-market</div>
          <div className="stat-value">{fmtNum(risk?.equity_estimate, 4)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">P/L realizado (FIFO sim)</div>
          <div className="stat-value">{fmtNum(risk?.realized_pnl, 4)}</div>
        </div>
        <div className="card">
          <div className="stat-label">P/L no realizado</div>
          <div className="stat-value">{fmtNum(risk?.unrealized_pnl, 4)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Comisiones estimadas acum.</div>
          <div className="stat-value">{fmtNum(risk?.fees_estimated, 4)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Drawdown actual</div>
          <div className="stat-value neg">
            {risk?.drawdown.current_drawdown_pct == null
              ? "Sin datos"
              : fmtPct(risk.drawdown.current_drawdown_pct)}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Drawdown máximo</div>
          <div className="stat-value neg">
            {risk?.drawdown.max_drawdown_pct == null
              ? "Sin datos"
              : fmtPct(risk.drawdown.max_drawdown_pct)}
          </div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Límites configurados</h3>
          <p>Exposición máx: {risk?.limits.max_exposure_pct ?? "Sin datos"}%</p>
          <p>Drawdown máx: {risk?.limits.max_drawdown_pct ?? "Sin datos"}%</p>
          <p>Pérdida diaria máx: {risk?.limits.max_daily_loss_pct ?? "Sin datos"}%</p>
          <p>Posiciones máx: {risk?.limits.max_positions ?? "Sin datos"}</p>
          <p>Trades/día máx: {risk?.limits.max_trades_per_day ?? "Sin datos"}</p>
          <p>Budget/trade: {risk?.limits.per_trade_budget ?? 25} USDT</p>
          <p>
            Brechas activas:{" "}
            {risk?.breaches?.length ? risk.breaches.join(", ") : "ninguna"}
          </p>
        </div>
        <div className="card">
          <h3>Clasificación de datos</h3>
          {risk &&
            Object.entries(risk.classification).map(([k, v]) => (
              <p key={k}>
                <strong>{k}</strong>: {v}
              </p>
            ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Exposición por activo</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Símbolo</th>
                <th>Costo</th>
                <th>Valor mercado</th>
                <th>P/L</th>
                <th>Valoración</th>
                <th>Fuente precio</th>
              </tr>
            </thead>
            <tbody>
              {(risk?.exposure_by_asset ?? []).length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    Sin posiciones
                  </td>
                </tr>
              ) : (
                risk!.exposure_by_asset.map((e) => (
                  <tr key={e.symbol}>
                    <td>{e.symbol}</td>
                    <td>{fmtNum(e.cost, 4)}</td>
                    <td>{fmtNum(e.market_value, 4)}</td>
                    <td>{fmtNum(e.unrealized_pnl, 4)}</td>
                    <td>{e.valuation}</td>
                    <td>{e.price_source ?? "Sin datos"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
