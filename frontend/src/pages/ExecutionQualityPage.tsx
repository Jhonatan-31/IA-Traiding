import { useEffect, useState } from "react";
import { api, fmtNum } from "../api";

export default function ExecutionQualityPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [costs, setCosts] = useState<Record<string, unknown> | null>(null);
  const [sim, setSim] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setError(null);
    try {
      const [s, c] = await Promise.all([
        api.executionQualityStatus(),
        api.executionQualityD28Costs(),
      ]);
      setStatus(s);
      setCosts(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function refreshAndSimulate() {
    setBusy(true);
    setError(null);
    try {
      await api.executionQualityRefreshBbo("BTCUSDT");
      const out = await api.executionQualitySimulate({
        side: "BUY",
        qty: 0.001,
        symbol: "BTCUSDT",
      });
      setSim(out);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const bbo = (status?.bbo as Record<string, unknown> | undefined) || {};
  const quotes = (bbo.quotes as Record<string, Record<string, unknown>> | undefined) || {};
  const reported = (costs?.reported as Record<string, unknown> | undefined) || {};
  const v2 = (sim?.v2 as Record<string, unknown> | undefined) || {};
  const cmp = (sim?.comparison as Record<string, unknown> | undefined) || {};

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Calidad de ejecución</h2>
          <p>
            Distingue cotización observada, simulación V1 (mid+proxy) y V2 (bid/ask).
            No activa bots ni altera carteras.
          </p>
        </div>
        <button className="btn primary" disabled={busy} onClick={() => void refreshAndSimulate()}>
          {busy ? "Actualizando…" : "Refrescar BBO + simular BUY 0.001 BTC"}
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      <section className="panel">
        <h3>Limitaciones</h3>
        <ul>
          {((status?.limitations as string[]) || []).map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
        <p className="muted">
          Motor V2: {String(status?.engine_v2 || "—")} · V1 preservado:{" "}
          {String(status?.engine_v1_preserved || "—")}
        </p>
      </section>

      <section className="panel">
        <h3>BBO observado (bookTicker público)</h3>
        <p className="muted">
          Conexión registro: {String(bbo.connected)} · símbolos: {String(bbo.n_symbols ?? 0)}
        </p>
        {Object.keys(quotes).length === 0 ? (
          <p className="muted">Sin cotizaciones en caché. Use el botón de refresco.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Símbolo</th>
                  <th>Bid</th>
                  <th>Ask</th>
                  <th>Spread</th>
                  <th>Edad ms</th>
                  <th>Calidad</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(quotes).map(([sym, q]) => (
                  <tr key={sym}>
                    <td>{sym}</td>
                    <td>{fmtNum(q.bid_price as number, 4)}</td>
                    <td>{fmtNum(q.ask_price as number, 4)}</td>
                    <td>{fmtNum(q.spread_abs as number, 4)}</td>
                    <td>{String(q.age_ms)}</td>
                    <td>{q.stale ? "STALE" : "FRESH"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel">
        <h3>Simulación comparativa (aislado)</h3>
        {!sim ? (
          <p className="muted">Aún sin simulación en esta sesión.</p>
        ) : (
          <div className="grid-2">
            <div>
              <h4>V2 ejecutable</h4>
              <p>Ref: {fmtNum(v2.ref_price as number, 4)}</p>
              <p>Ejecutable: {fmtNum(v2.executable_price as number, 4)}</p>
              <p>All-in: {fmtNum(v2.price_all_in as number, 4)}</p>
              <p>Fee: {fmtNum(v2.fee_total as number, 6)}</p>
              <p>Slip: {fmtNum(v2.slip_total as number, 6)}</p>
              <p>Costo total est.: {fmtNum(v2.total_cost_est as number, 6)}</p>
              <p>Calidad datos: {String(v2.data_quality)}</p>
              <p>Partial: {String(v2.partial)}</p>
            </div>
            <div>
              <h4>Δ vs modelo V1</h4>
              <p>
                pl_delta (aprox):{" "}
                {fmtNum(cmp.pl_delta_v2_minus_model_gap as number | null, 6)}
              </p>
              <p className="muted">{String(cmp.interpretation || "")}</p>
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <h3>Costos D28H5 (artefacto congelado)</h3>
        <p className="muted">
          Hash: {String(costs?.config_hash)} · match: {String(costs?.hash_match)}
        </p>
        <p>Total fricciones: {String(reported.total)} USDT</p>
        <p>
          Fee / Slip / Spread: {String(reported.fee)} / {String(reported.slip)} /{" "}
          {String(reported.spread)}
        </p>
        <p>
          Rebalances: {String(reported.rebalances_real)} · Turnover events:{" "}
          {String(reported.turnover_events)} · Notional: {String(reported.notional_traded)}
        </p>
        <p className="muted">{String(costs?.explanation || "")}</p>
      </section>
    </div>
  );
}
