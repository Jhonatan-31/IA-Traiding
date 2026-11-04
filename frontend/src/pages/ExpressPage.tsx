import { useEffect, useState } from "react";
import { api, fmtNum, fmtTime } from "../api";

export default function ExpressPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await api.expressStatus();
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Error");
      }
    };
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const sec = Number(data?.seconds_remaining ?? 0);
  const mm = Math.floor(sec / 60);
  const ss = Math.floor(sec % 60);
  const decisions = (data?.decisions as Array<Record<string, unknown>>) || [];
  const rejects = (data?.rejects as Array<Record<string, unknown>>) || [];
  const positions = (data?.positions as Array<Record<string, unknown>>) || [];
  const dc = (data?.decision_counts as Record<string, number>) || {};
  const st = (data?.state as Record<string, unknown>) || {};

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Express Test</h2>
          <p>
            Cartera aislada <code>express_test_20261103</code> · 100 USDT · fin absoluto
            20:00 Bogotá / 01:00 UTC · PAPER_ONLY · sin tocar SMA/Lab/Shadow
          </p>
        </div>
        <div>
          <span className={data?.ended ? "pill warn" : "pill ok"}>
            {data?.ended ? "ENDED" : String(st.status || "…")}
          </span>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))",
          gap: 12,
          marginBottom: 14,
        }}
      >
        <div className="card">
          <h3>Tiempo restante</h3>
          <p style={{ fontSize: 28, margin: 0 }}>
            {data?.ended ? "0:00" : `${mm}:${String(ss).padStart(2, "0")}`}
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            Deadline {fmtTime(data?.deadline_utc as string)}
          </p>
        </div>
        <div className="card">
          <h3>Patrimonio</h3>
          <p>Bruto: {fmtNum(data?.equity_gross as number, 2)}</p>
          <p>Cash: {fmtNum(data?.cash as number, 2)}</p>
          <p>Neto si liquidara*: {fmtNum(data?.equity_net_if_liquidate_est as number, 2)}</p>
          <p className="muted" style={{ fontSize: 11 }}>
            {String(data?.liquidation_note || "")}
          </p>
        </div>
        <div className="card">
          <h3>P/L</h3>
          <p>Realizado: {fmtNum(data?.realized_pnl as number, 4)}</p>
          <p>No realizado: {fmtNum(data?.unrealized_pnl as number, 4)}</p>
          <p>
            Fees {fmtNum(data?.fees as number, 4)} · slip {fmtNum(data?.slip as number, 4)}
          </p>
        </div>
        <div className="card">
          <h3>Decisiones / conexión</h3>
          <p>
            B{dc.BUY ?? 0} / S{dc.SELL ?? 0} / H{dc.HOLD ?? 0}
          </p>
          <p>
            Ciclos: {String(st.cycle_count ?? "—")} · conn{" "}
            {String(st.connection_ok ?? "—")}
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            probability_validated={String(data?.probability_validated)} (score ≠
            probabilidad)
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Posiciones abiertas</h3>
        <table className="data">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Mark</th>
              <th>uPnL</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={String(p.symbol)}>
                <td>{String(p.symbol)}</td>
                <td>{fmtNum(p.qty as number, 6)}</td>
                <td>{fmtNum(p.entry_price as number, 4)}</td>
                <td>{fmtNum(p.mark as number, 4)}</td>
                <td>{fmtNum(p.upnl as number, 4)}</td>
              </tr>
            ))}
            {!positions.length && (
              <tr>
                <td colSpan={5} className="muted">
                  Sin posiciones
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Últimas decisiones</h3>
        <table className="data">
          <thead>
            <tr>
              <th>At</th>
              <th>Symbol</th>
              <th>Action</th>
              <th>Score</th>
              <th>Reason</th>
              <th>Price</th>
            </tr>
          </thead>
          <tbody>
            {decisions.slice(0, 20).map((d) => (
              <tr key={String(d.id)}>
                <td>{fmtTime(d.at as string)}</td>
                <td>{String(d.symbol)}</td>
                <td>{String(d.action)}</td>
                <td>{fmtNum(d.signal_score as number, 2)}</td>
                <td>{String(d.reason)}</td>
                <td>{fmtNum(d.observed_price as number, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Rechazos</h3>
        <table className="data">
          <thead>
            <tr>
              <th>At</th>
              <th>Symbol</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {rejects.slice(0, 15).map((r) => (
              <tr key={String(r.id)}>
                <td>{fmtTime(r.at as string)}</td>
                <td>{String(r.symbol)}</td>
                <td>{String(r.reason)}</td>
              </tr>
            ))}
            {!rejects.length && (
              <tr>
                <td colSpan={3} className="muted">
                  Sin rechazos
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
