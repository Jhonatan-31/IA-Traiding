import { useEffect, useState } from "react";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  fmtNum,
  fmtPct,
  fmtTime,
  type Overview,
  type Position,
  type Scan,
} from "../api";

export default function OverviewPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [scans, setScans] = useState<Scan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setError(null);
      const [o, p, s] = await Promise.all([
        api.overview(),
        api.positions(),
        api.scans(),
      ]);
      setOverview(o);
      setPositions(p);
      setScans(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de carga");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30000);
    return () => clearInterval(id);
  }, []);

  if (loading && !overview) {
    return <p className="muted">Cargando resumen…</p>;
  }

  const equity = overview?.equity_estimate ?? null;
  const initial = overview?.initial_capital ?? 1000;
  const pnl =
    equity != null ? equity - initial : null;
  const pnlPct = pnl != null ? (pnl / initial) * 100 : null;
  const unrealized = positions.reduce(
    (acc, p) => acc + (p.unrealized_pnl ?? 0),
    0
  );

  const chartData = scans.map((s) => ({
    t: new Date(s.at).toLocaleString("es-CO", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
    }),
    equity: s.equity,
  }));

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Resumen general</h2>
          <p>Capital virtual y estado del motor en modo PAPER_ONLY.</p>
        </div>
        <div className="actions">
          <span className={`pill ${overview?.engine?.paused ? "warn" : "ok"}`}>
            {overview?.engine?.paused ? "PAUSADO" : "MOTOR ACTIVO"}
          </span>
          <button className="btn" onClick={() => void load()}>
            Actualizar
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="grid stats" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="stat-label">Capital inicial</div>
          <div className="stat-value">{fmtNum(initial, 2)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">Patrimonio estimado</div>
          <div className="stat-value">{fmtNum(equity, 4)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">Efectivo</div>
          <div className="stat-value">{fmtNum(overview?.cash, 2)} USDT</div>
        </div>
        <div className="card">
          <div className="stat-label">Capital invertido (costo)</div>
          <div className="stat-value">
            {fmtNum(overview?.invested_cost, 2)} USDT
          </div>
        </div>
        <div className="card">
          <div className="stat-label">P/L no realizado</div>
          <div className={`stat-value ${unrealized >= 0 ? "pos" : "neg"}`}>
            {fmtNum(unrealized, 4)} USDT
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Rendimiento vs inicial</div>
          <div className={`stat-value ${(pnl ?? 0) >= 0 ? "pos" : "neg"}`}>
            {fmtPct(pnlPct)}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Posiciones abiertas</div>
          <div className="stat-value">{overview?.positions ?? "Sin datos"}</div>
        </div>
        <div className="card">
          <div className="stat-label">Mercados último ciclo</div>
          <div className="stat-value">
            {overview?.latest?.markets ?? "Sin datos"}
          </div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "2fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Historial de patrimonio (scans)</h3>
          {chartData.length < 2 ? (
            <p className="muted">
              Aún no hay suficientes puntos de equity. El worker registra un punto
              por ciclo.
            </p>
          ) : (
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <XAxis dataKey="t" stroke="#8fa3bb" fontSize={11} />
                  <YAxis
                    domain={["auto", "auto"]}
                    stroke="#8fa3bb"
                    fontSize={11}
                    width={70}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#121a2b",
                      border: "1px solid #2a3a55",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="equity"
                    stroke="#2dd4bf"
                    strokeWidth={2}
                    dot={false}
                    name="Equity USDT"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        <div className="card">
          <h3>Exposición por activo</h3>
          {positions.length === 0 ? (
            <p className="muted">Sin posiciones abiertas.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Par</th>
                    <th>Valor</th>
                    <th>P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{fmtNum(p.market_value, 4)}</td>
                      <td>{fmtNum(p.unrealized_pnl, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
            Último ciclo: {fmtTime(overview?.latest?.at)} · Errores:{" "}
            {overview?.latest?.errors ?? "Sin datos"} · Estrategia:{" "}
            {overview?.strategy ?? "Sin datos"}
          </p>
        </div>
      </div>
    </div>
  );
}
