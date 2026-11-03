import { useEffect, useState } from "react";
import { api, fmtNum, type Overview } from "../api";

export default function RiskPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setOverview(await api.overview());
  }

  useEffect(() => {
    void load().catch((e) =>
      setError(e instanceof Error ? e.message : "Error")
    );
  }, []);

  async function toggle() {
    if (!overview) return;
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      if (overview.engine?.paused) {
        await api.resume("dashboard_resume");
        setMsg("Simulación reanudada. No se borraron datos.");
      } else {
        await api.pause("dashboard_pause");
        setMsg("Simulación pausada: no habrá nuevas entradas/salidas.");
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const equity = overview?.equity_estimate ?? null;
  const initial = overview?.initial_capital ?? 1000;
  const drawdownPct =
    equity != null ? Math.min(0, ((equity - initial) / initial) * 100) : null;

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Gestión de riesgo</h2>
          <p>
            Controles paper-only. Límites avanzados (correlación, circuit breaker
            automático) se ampliarán en Etapa D.
          </p>
        </div>
        <button
          className={`btn ${overview?.engine?.paused ? "primary" : "danger"}`}
          disabled={busy || !overview}
          onClick={() => void toggle()}
        >
          {overview?.engine?.paused ? "REANUDAR SIMULACIÓN" : "PAUSAR SIMULACIÓN"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {msg && (
        <div className="card" style={{ marginBottom: 14, borderColor: "#2dd4bf" }}>
          {msg}
        </div>
      )}
      <div className="grid stats">
        <div className="card">
          <div className="stat-label">Estado motor</div>
          <div className="stat-value" style={{ fontSize: 18 }}>
            {overview?.engine?.paused ? "PAUSADO" : "ACTIVO"}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Exposición abierta (costo)</div>
          <div className="stat-value">{fmtNum(overview?.invested_cost, 2)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">Posiciones</div>
          <div className="stat-value">{overview?.positions ?? "Sin datos"} / 10</div>
        </div>
        <div className="card">
          <div className="stat-label">Drawdown vs inicial (aprox.)</div>
          <div className="stat-value neg">
            {drawdownPct == null ? "Sin datos" : `${drawdownPct.toFixed(2)}%`}
          </div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <h3>Reglas activas hoy</h3>
        <ul className="muted">
          <li>Presupuesto por entrada: máx. 25 USDT</li>
          <li>Máximo 10 posiciones simultáneas</li>
          <li>Fee/slippage simulados: 0.1% cada uno</li>
          <li>Pausa: bloquea nuevas entradas/salidas; conserva historial</li>
          <li>Correlación / pérdida máxima diaria: Sin datos (pendiente)</li>
        </ul>
      </div>
    </div>
  );
}
