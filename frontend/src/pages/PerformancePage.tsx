import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtNum, fmtTime } from "../api";

type ComparePayload = {
  generated_at?: string;
  note?: string;
  ledgers?: {
    sma_paper?: Record<string, unknown>;
    lab_auto?: Record<string, unknown>;
    research_sim?: Record<string, unknown>;
  };
  shadow_live?: Record<string, unknown>;
  integrity?: Record<string, unknown>;
  equity_curves?: {
    sma_scans?: Array<{ t: string; equity: number | null; scan_id: number }>;
    lab_daily?: Array<{
      day: string;
      start_equity: number | null;
      end_equity: number | null;
    }>;
    note?: string;
  };
  operational_coverage?: {
    downtime_gaps?: Array<Record<string, unknown>>;
    host_sleep_confirmed_utc?: Record<string, string>;
    policy?: string;
  };
};

export default function PerformancePage() {
  const [data, setData] = useState<ComparePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const payload = await api.performanceCompare();
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Error");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const sma = data?.ledgers?.sma_paper || {};
  const lab = data?.ledgers?.lab_auto || {};
  const research = data?.ledgers?.research_sim || {};
  const shadow = data?.shadow_live || {};
  const dd = (sma.drawdown as Record<string, unknown>) || {};
  const gaps = data?.operational_coverage?.downtime_gaps || [];
  const sleep = data?.operational_coverage?.host_sleep_confirmed_utc || {};
  const smaCurve = (data?.equity_curves?.sma_scans || []).map((p) => ({
    label: fmtTime(p.t),
    sma: p.equity,
  }));
  const labCurve = (data?.equity_curves?.lab_daily || []).flatMap((p) => [
    { label: `${p.day} start`, lab: p.start_equity },
    { label: `${p.day} end`, lab: p.end_equity },
  ]);

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Resultados</h2>
          <p>
            Etapa Q · tres ledgers separados · solo hechos persistidos. Shadow PENDING no
            inventa PnL. PAPER_ONLY.
          </p>
        </div>
        <button
          className="btn"
          onClick={() => {
            setLoading(true);
            void api
              .performanceCompare()
              .then(setData)
              .catch((e) => setError(e instanceof Error ? e.message : "Error"))
              .finally(() => setLoading(false));
          }}
        >
          {loading ? "Cargando…" : "Actualizar"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}
      <p className="muted" style={{ fontSize: 12 }}>
        Generado: {fmtTime(data?.generated_at)} · {data?.note}
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))",
          gap: 12,
          marginBottom: 14,
        }}
      >
        <div className="card">
          <h3>SMA paper</h3>
          <p>Capital inicial: {fmtNum(sma.initial_capital as number | null, 2)}</p>
          <p>Cash: {fmtNum(sma.cash as number | null, 2)}</p>
          <p>Invertido: {fmtNum(sma.invested_cost as number | null, 2)}</p>
          <p>Equity MTM: {fmtNum(sma.equity_estimate as number | null, 2)}</p>
          <p>Retorno neto: {fmtNum(sma.net_return_vs_initial as number | null, 6)}</p>
          <p>uPnL: {fmtNum(sma.unrealized_pnl as number | null, 4)}</p>
          <p>rPnL: {fmtNum(sma.realized_pnl as number | null, 4)}</p>
          <p>Fees est.: {fmtNum(sma.fees_estimated as number | null, 4)}</p>
          <p>
            Max DD: {fmtNum(dd.max_drawdown_pct as number | null, 4)}% · peak{" "}
            {fmtNum(dd.peak_equity as number | null, 2)}
          </p>
          <p>
            Posiciones: {String(sma.open_positions ?? "—")} · trades{" "}
            {String(sma.trades_total ?? "—")} (B{String(sma.buys ?? 0)}/S
            {String(sma.sells ?? 0)})
          </p>
        </div>
        <div className="card">
          <h3>Lab auto</h3>
          <p>
            Estado:{" "}
            <span className="pill info">{String(lab.valuation_status ?? "—")}</span>
          </p>
          <p>Capital inicial: {fmtNum(lab.initial_capital as number | null, 2)}</p>
          <p>Cash: {fmtNum(lab.cash as number | null, 2)}</p>
          <p>Equity MTM: {fmtNum(lab.equity_estimate as number | null, 2)}</p>
          <p>Retorno neto: {fmtNum(lab.net_return_vs_initial as number | null, 6)}</p>
          <p>Realizado: {fmtNum(lab.realized_pnl as number | null, 4)}</p>
          <p>uPnL: {fmtNum(lab.unrealized_pnl as number | null, 4)}</p>
          <p>
            Fees: {fmtNum(lab.fees_accumulated as number | null, 4)} · slip{" "}
            {fmtNum(lab.slip_total as number | null, 4)}
          </p>
          <p>DD vs peak: {fmtNum(lab.drawdown_vs_peak as number | null, 6)}</p>
          <p>Posiciones abiertas: {String(lab.open_positions ?? "—")}</p>
        </div>
        <div className="card">
          <h3>Research sim (Shadow)</h3>
          <p>Cash: {fmtNum(research.cash as number | null, 2)}</p>
          <p className="muted" style={{ fontSize: 12 }}>
            {String(research.note || "")}
          </p>
          <p>
            Shadow LIVE: pending {String(shadow.pending ?? "—")} · resolved{" "}
            {String(shadow.resolved ?? "—")} · invalid {String(shadow.invalid ?? "—")} ·
            outcomes {String(shadow.outcomes_persisted ?? "—")} · ready_now{" "}
            {String(shadow.ready_now ?? "—")}
          </p>
          <p>
            Muestra suficiente:{" "}
            <span className={shadow.sample_sufficient ? "pill ok" : "pill warn"}>
              {String(shadow.sample_sufficient ?? false)}
            </span>
            {" · "}claim estrategia:{" "}
            <span className="pill warn">{String(shadow.strategy_claim_allowed ?? false)}</span>
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            Primer horizonte listo:{" "}
            {fmtTime(shadow.earliest_horizon_ready_after_utc as string)}
            {shadow.pending_reason_summary
              ? ` · ~${String(
                  (shadow.pending_reason_summary as Record<string, unknown>)
                    .seconds_until_first_ready ?? "—"
                )}s · ${String(
                  (shadow.pending_reason_summary as Record<string, unknown>).primary ?? ""
                )}`
              : ""}
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            {String(shadow.pnl_note || "")}
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            Eval predictiva ≠ cartera ejecutable. HOLD ≠ venta.
          </p>
          {!((shadow.resolved_predictions as unknown[]) || []).length && (
            <p className="muted" style={{ fontSize: 12 }}>
              Predicciones resueltas: ninguna todavía.
            </p>
          )}
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Evolución patrimonial (observada)</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          {data?.equity_curves?.note}
        </p>
        <div style={{ width: "100%", height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={smaCurve.length ? smaCurve : labCurve}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} width={64} />
              <Tooltip />
              <Legend />
              {smaCurve.length > 0 && (
                <Line
                  type="monotone"
                  dataKey="sma"
                  name="SMA scans"
                  stroke="#1f6feb"
                  dot={false}
                  strokeWidth={2}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
        {labCurve.length > 0 && (
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Lab daily:{" "}
            {labCurve
              .map((p) => `${p.label}=${fmtNum(p.lab as number | null, 2)}`)
              .join(" · ")}
          </p>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Cobertura operativa / suspensión</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          {data?.operational_coverage?.policy}
        </p>
        <p style={{ fontSize: 13 }}>
          Host sleep: {String(sleep.sleep || "—")} → wake {String(sleep.wake || "—")} (
          {String(sleep.source || "")})
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Tabla</th>
                <th>Gap s</th>
                <th>~Ciclos omitidos</th>
                <th>Reanudó</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((g, i) => (
                <tr key={i}>
                  <td>{String(g.table)}</td>
                  <td>{String(g.gap_sec)}</td>
                  <td>{String(g.approx_cycles_omitted)}</td>
                  <td>{fmtTime(g.resumed_at as string)}</td>
                </tr>
              ))}
              {!gaps.length && (
                <tr>
                  <td colSpan={4} className="muted">
                    Sin huecos &gt;450s
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Lab por símbolo / cierres</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Buys</th>
                <th>Sells</th>
                <th>Fees</th>
                <th>Slip</th>
                <th>rPnL</th>
              </tr>
            </thead>
            <tbody>
              {((lab.by_symbol as Array<Record<string, unknown>>) || []).map((r) => (
                <tr key={String(r.symbol)}>
                  <td>{String(r.symbol)}</td>
                  <td>{String(r.buys)}</td>
                  <td>{String(r.sells)}</td>
                  <td>{fmtNum(r.fees as number, 4)}</td>
                  <td>{fmtNum(r.slip as number, 4)}</td>
                  <td>{fmtNum(r.realized_pnl as number, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table className="data">
            <thead>
              <tr>
                <th>Cierre</th>
                <th>Symbol</th>
                <th>rPnL</th>
                <th>Reason</th>
                <th>Demo/verif?</th>
              </tr>
            </thead>
            <tbody>
              {((lab.closed_sells as Array<Record<string, unknown>>) || []).map((t) => (
                <tr key={String(t.id)}>
                  <td>{fmtTime(t.at as string)}</td>
                  <td>{String(t.symbol)}</td>
                  <td>{fmtNum(t.realized_pnl as number, 4)}</td>
                  <td>{String(t.reason)}</td>
                  <td>{String(t.is_verification_or_demo)}</td>
                </tr>
              ))}
              {!((lab.closed_sells as unknown[]) || []).length && (
                <tr>
                  <td colSpan={5} className="muted">
                    Sin ventas cerradas
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Posiciones Lab</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Cost</th>
                <th>Entry</th>
              </tr>
            </thead>
            <tbody>
              {((lab.positions as Array<Record<string, unknown>>) || []).map((p) => (
                <tr key={String(p.symbol)}>
                  <td>{String(p.symbol)}</td>
                  <td>{fmtNum(p.qty as number, 6)}</td>
                  <td>{fmtNum(p.cost as number, 2)}</td>
                  <td>{fmtNum(p.entry_price as number, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Posiciones SMA paper</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {((sma.positions as Array<Record<string, unknown>>) || []).map((p) => (
                <tr key={String(p.symbol)}>
                  <td>{String(p.symbol)}</td>
                  <td>{fmtNum(p.qty as number, 6)}</td>
                  <td>{fmtNum(p.cost as number, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Integridad: ledgers separados=
          {String(data?.integrity?.ledgers_separated)} · paper_only=
          {String(data?.integrity?.paper_only)} · shadow_executing=
          {String(data?.integrity?.shadow_executing)} · paper_ai_disabled=
          {String(data?.integrity?.paper_ai_disabled)}
        </p>
      </div>
    </div>
  );
}
