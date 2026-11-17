import { useEffect, useState } from "react";
import { api, fmtNum } from "../api";

type Dict = Record<string, unknown>;

export default function ExecutionQualityPage() {
  const [status, setStatus] = useState<Dict | null>(null);
  const [costs, setCosts] = useState<Dict | null>(null);
  const [audit, setAudit] = useState<Dict | null>(null);
  const [sim, setSim] = useState<Dict | null>(null);
  const [compare, setCompare] = useState<Dict | null>(null);
  const [capturePlan, setCapturePlan] = useState<Dict | null>(null);
  const [captureRun, setCaptureRun] = useState<Dict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setError(null);
    try {
      const [s, c, a, plan] = await Promise.all([
        api.executionQualityStatus(),
        api.executionQualityD28Costs(),
        api.executionQualityAudit(),
        api.executionQualityCapturePlan(),
      ]);
      setStatus(s);
      setCosts(c);
      setAudit(a);
      setCapturePlan(plan);
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
      await api.executionQualityRefreshBbo("BTCUSDT,ETHUSDT,SOLUSDT");
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

  async function runCompare() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.executionQualityCompareOnce({
        side: "BUY",
        qty: 0.001,
        symbol: "BTCUSDT",
      });
      setCompare(out);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function runBoundedCapture() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.executionQualityCaptureBounded(5);
      setCaptureRun(out);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const bbo = (status?.bbo as Dict | undefined) || {};
  const quotes = (bbo.quotes as Record<string, Dict> | undefined) || {};
  const reported = (costs?.reported as Dict | undefined) || {};
  const v2 = (sim?.v2 as Dict | undefined) || {};
  const cmp = (sim?.comparison as Dict | undefined) || {};
  const obs = (compare?.observation as Dict | undefined) || {};
  const summary = (compare?.summary as Dict | undefined) || {};
  const lab = (audit?.lab_accounting as Dict | undefined) || {};
  const disk = (capturePlan?.disk as Dict | undefined) || {};

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Calidad de ejecución</h2>
          <p>
            Cotización observada · precio estimado ejecutable · fill simulado.
            No es operación paper ni real. No altera carteras.
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button className="btn primary" disabled={busy} onClick={() => void refreshAndSimulate()}>
            {busy ? "Actualizando…" : "Refrescar BBO + simular"}
          </button>
          <button className="btn" disabled={busy} onClick={() => void runCompare()}>
            Comparar V1/V2
          </button>
          <button className="btn" disabled={busy} onClick={() => void runBoundedCapture()}>
            Captura acotada 5s
          </button>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      <section className="panel">
        <h3>Etiquetas (no confundir)</h3>
        <ul>
          <li>PRECIO OBSERVADO — bid/ask bookTicker público</li>
          <li>PRECIO ESTIMADO EJECUTABLE — ask/bid ± slip modelo</li>
          <li>FILL SIMULADO — V1 mid+proxy o V2 BBO (aislado)</li>
          <li>OPERACIÓN PAPER / REAL — no se generan aquí</li>
        </ul>
        <p className="muted">
          Motor V2: {String(status?.engine_v2 || "—")} · V1 preservado:{" "}
          {String(status?.engine_v1_preserved || "—")} · mutates_ledgers:{" "}
          {String(status?.mutates_ledgers)}
        </p>
        <p className="muted">
          Lab SELL: {String(lab.sell_cash_model || "—")} · histórico:{" "}
          {String(lab.historical_lab_sells || "—")}
        </p>
      </section>

      <section className="panel">
        <h3>Limitaciones</h3>
        <ul>
          {((status?.limitations as string[]) || []).map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h3>BBO observado (bookTicker público)</h3>
        <p className="muted">
          Conexión: {String(bbo.connected)} · sync: {String(bbo.sync_state)} ·
          aceptados: {String(bbo.n_accepted ?? 0)} · stale: {String(bbo.n_stale ?? 0)} ·
          rejects: {JSON.stringify(bbo.reject_counts || {})}
        </p>
        {Object.keys(quotes).length === 0 ? (
          <p className="muted">Sin cotizaciones en caché. Use refresco o captura acotada.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Símbolo</th>
                  <th>Bid / qty</th>
                  <th>Ask / qty</th>
                  <th>Spread</th>
                  <th>Edad ms</th>
                  <th>Update ID</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(quotes).map(([sym, q]) => (
                  <tr key={sym}>
                    <td>{sym}</td>
                    <td>
                      {fmtNum(q.bid_price as number, 4)} / {fmtNum(q.bid_qty as number, 4)}
                    </td>
                    <td>
                      {fmtNum(q.ask_price as number, 4)} / {fmtNum(q.ask_qty as number, 4)}
                    </td>
                    <td>{fmtNum(q.spread_abs as number, 4)}</td>
                    <td>{String(q.age_ms)}</td>
                    <td>{String(q.update_id ?? "—")}</td>
                    <td>{q.stale ? "STALE" : "FRESH"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted">{String(bbo.note || "")}</p>
      </section>

      <section className="panel">
        <h3>Simulación V2 (aislado)</h3>
        {!sim ? (
          <p className="muted">Aún sin simulación en esta sesión.</p>
        ) : (
          <div className="grid-2">
            <div>
              <h4>V2 estimado ejecutable</h4>
              <p>Fuente: {String((sim.bbo_used as Dict | undefined)?.source || "sin BBO")}</p>
              <p>Ref mid: {fmtNum(v2.ref_price as number, 4)}</p>
              <p>Ejecutable: {fmtNum(v2.executable_price as number, 4)}</p>
              <p>All-in: {fmtNum(v2.price_all_in as number, 4)}</p>
              <p>Fee / slip: {fmtNum(v2.fee_total as number, 6)} / {fmtNum(v2.slip_total as number, 6)}</p>
              <p>Qty pedida / fill: {fmtNum(v2.qty_requested as number, 6)} / {fmtNum(v2.fill_qty as number, 6)}</p>
              <p>Partial: {String(v2.partial)} · calidad: {String(v2.data_quality)}</p>
              <p>Motivo rechazo: {v2.ok === false ? String(v2.reason) : "—"}</p>
            </div>
            <div>
              <h4>Δ vs modelo V1</h4>
              <p>
                pl_delta (aprox): {fmtNum(cmp.pl_delta_v2_minus_model_gap as number | null, 6)}
              </p>
              <p className="muted">{String(cmp.interpretation || "")}</p>
            </div>
          </div>
        )}
      </section>

      <section className="panel">
        <h3>Experimento V1 vs V2</h3>
        {!compare ? (
          <p className="muted">Ejecute «Comparar V1/V2» para una observación controlada.</p>
        ) : (
          <>
            <p>
              Estado: {String(obs.status)} · comparable: {String(obs.comparable)} ·
              motivo: {String(obs.reason || "—")}
            </p>
            <p>
              Precio V1 / V2: {fmtNum(obs.price_v1 as number, 4)} / {fmtNum(obs.price_v2 as number, 4)}
            </p>
            <p>
              Diff precio: {fmtNum(obs.price_diff_v2_minus_v1_signed as number, 6)} ·
              gap costo: {fmtNum(obs.cost_gap_adverse_to_trader as number, 6)}
            </p>
            <p>
              Observaciones comparables: {String(summary.n_comparable ?? 0)} ·
              no comparables: {String(summary.n_not_comparable ?? 0)} ·
              fabricadas: {String(summary.fabricated_observations)}
            </p>
            <p className="muted">{String(obs.accounting_note || summary.interpretation || "")}</p>
          </>
        )}
      </section>

      <section className="panel">
        <h3>Captura experimental (acotada)</h3>
        <p className="muted">
          Plan: {String((capturePlan?.plan as Dict | undefined)?.max_seconds ?? "—")}s ·
          est. bytes: {String(disk.estimated_bytes ?? "—")} · 24/7:{" "}
          {String(capturePlan?.permanent_24_7)} (requiere autorización)
        </p>
        {captureRun ? (
          <p>
            Eventos: {String(captureRun.n_events)} · duplicados: {String(captureRun.n_duplicates)} ·
            huecos: {String(captureRun.n_gaps)} · errores: {String(captureRun.n_errors)} ·
            permanente: {String(captureRun.permanent_service)}
          </p>
        ) : (
          <p className="muted">Sin captura en esta sesión. No hay gráfico BBO histórico inventado.</p>
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
        <p className="muted">{String(costs?.explanation || "")}</p>
      </section>
    </div>
  );
}
