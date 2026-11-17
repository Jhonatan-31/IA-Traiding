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
  const [anomaly, setAnomaly] = useState<Dict | null>(null);
  const [experiment, setExperiment] = useState<Dict | null>(null);
  const [labAudit, setLabAudit] = useState<Dict | null>(null);
  const [fair, setFair] = useState<Dict | null>(null);
  const [fairOnce, setFairOnce] = useState<Dict | null>(null);
  const [dual, setDual] = useState<Dict | null>(null);
  const [fairFilter, setFairFilter] = useState("BTCUSDT|BUY");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setError(null);
    try {
      const [s, c, a, plan, anom, exp, lab, dualL] = await Promise.all([
        api.executionQualityStatus(),
        api.executionQualityD28Costs(),
        api.executionQualityAudit(),
        api.executionQualityCapturePlan(),
        api.executionQualityAlAnomaly(),
        api.executionQualityExperimentLatest(),
        api.executionQualityLabSellsAudit(),
        api.executionQualityDualLatest(),
      ]);
      setStatus(s);
      setCosts(c);
      setAudit(a);
      setCapturePlan(plan);
      setAnomaly(anom);
      setExperiment(exp);
      setLabAudit(lab);
      setDual(dualL);
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

  async function loadFair() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.executionQualityFairCompare("am");
      setFair(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function runFairOnce() {
    setBusy(true);
    setError(null);
    try {
      const out = await api.executionQualityCompareFairOnce({
        side: "BUY",
        qty: 0.001,
        symbol: "BTCUSDT",
      });
      setFairOnce(out);
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
  const expBody = (experiment?.experiment as Dict | undefined) || {};
  const expSummary = (expBody.analysis_summary as Dict | undefined) || {};
  const expManifest = (expBody.manifest as Dict | undefined) || {};
  const decomp = (anomaly?.decomposition as Dict | undefined) || {};

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
          <button className="btn" disabled={busy} onClick={() => void loadFair()}>
            Fair-compare AM
          </button>
          <button className="btn" disabled={busy} onClick={() => void runFairOnce()}>
            LEGACY+MATCHED once
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
        <h3>Comparación económica justa V1 / V2</h3>
        <p className="muted">
          Modos LEGACY (defaults) y MATCHED (fee+slip iguales; aísla mid→touch). No es
          rentabilidad. Ventana corta ≠ todos los regímenes. Sin controles de trading.
        </p>
        <p>
          Filtro grupo:{" "}
          <select value={fairFilter} onChange={(e) => setFairFilter(e.target.value)}>
            {["BTCUSDT|BUY", "BTCUSDT|SELL", "ETHUSDT|BUY", "ETHUSDT|SELL", "SOLUSDT|BUY", "SOLUSDT|SELL"].map(
              (k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              )
            )}
          </select>
        </p>
        {fair?.ok ? (
          <>
            <p className="muted">
              Independencia:{" "}
              {String(
                ((fair.analysis as Dict)?.independence as Dict | undefined)?.note || ""
              )}
            </p>
            {(["legacy", "matched"] as const).map((mode) => {
              const block = ((fair.analysis as Dict)?.[mode] as Dict) || {};
              const grp =
                ((block.by_symbol_side as Record<string, Dict> | undefined) || {})[fairFilter] ||
                {};
              const diff = (grp.diff_bps as Dict | undefined) || {};
              return (
                <div key={mode}>
                  <h4>{mode.toUpperCase()}</h4>
                  <p>
                    Filas derivadas: {String(block.n_comparable)} · buckets únicos grupo:{" "}
                    {String(grp.n_unique_buckets ?? "—")} · mediana diff bps:{" "}
                    {fmtNum(diff.p50 as number | null, 4)} · incompletos L2:{" "}
                    {String(grp.n_incomplete_l2 ?? "—")}
                  </p>
                </div>
              );
            })}
          </>
        ) : (
          <p className="muted">Cargue fair-compare AM (dataset en disco) o espere captura AN.</p>
        )}
        {fairOnce && (
          <div className="grid-2">
            <div>
              <h4>LEGACY once</h4>
              <p>
                Δ precio:{" "}
                {fmtNum(
                  ((fairOnce.legacy as Dict | undefined)?.price_diff_v2_minus_v1_signed as number) ??
                    null,
                  4
                )}
              </p>
            </div>
            <div>
              <h4>MATCHED once</h4>
              <p>
                Δ bps:{" "}
                {fmtNum(((fairOnce.matched as Dict | undefined)?.diff_bps_vs_mid as number) ?? null, 4)}
              </p>
              <p className="muted">
                {String(((fairOnce.matched as Dict | undefined)?.cause as string) || "")}
              </p>
            </div>
          </div>
        )}
        {dual?.ok && (
          <p className="muted">
            Dual REST/WS: REST eventos{" "}
            {String(((dual.experiment as Dict)?.rest as Dict | undefined)?.n_events)} · WS{" "}
            {String(((dual.experiment as Dict)?.ws as Dict | undefined)?.n_events)} · rate{" "}
            {String(((dual.experiment as Dict)?.ws as Dict | undefined)?.msg_rate)}
          </p>
        )}
      </section>

      <section className="panel">
        <h3>AM1 — ¿Por qué V2 pareció más barato en AL?</h3>
        {!anomaly ? (
          <p className="muted">Sin reconstrucción.</p>
        ) : (
          <>
            <p className="muted">{String(anomaly.original_verdict)}</p>
            <p>
              Diff unitario V2−V1: {fmtNum(anomaly.diff_unit_v2_minus_v1 as number, 4)} ·
              cash 0.001 BTC: {fmtNum(anomaly.diff_cash_v2_minus_v1 as number, 6)}
            </p>
            <p className="muted">{String(decomp.primary_cause || "")}</p>
          </>
        )}
      </section>

      <section className="panel">
        <h3>Experimento de precios ejecutables</h3>
        <p className="muted">
          DATOS OBSERVADOS · DECISIONES HIPOTÉTICAS · FILL ESTIMADO · no es OPERACIÓN PAPER.
          Captura permanente: no disponible en UI.
        </p>
        {experiment?.ok ? (
          <>
            <p>
              Inicio ms: {String(expManifest.started_at_ms ?? expBody.started_at_ms)} · fin:{" "}
              {String(expManifest.ended_at_ms ?? expBody.ended_at_ms)} · duración ms:{" "}
              {String(expManifest.duration_ms ?? "—")}
            </p>
            <p>
              Símbolos: {JSON.stringify(expManifest.symbols || expBody.symbols || [])} ·
              eventos: {String(expBody.n_events)} · stop: {String(expBody.stop_reason)} ·
              bytes: {String(expBody.bytes_written)}
            </p>
            <p>
              Comparables: {String(expSummary.n_comparable ?? "—")} · rechazados:{" "}
              {String(expSummary.n_rejected ?? "—")}
            </p>
            <p>
              Diff precio mediana V2−V1:{" "}
              {fmtNum(
                ((expSummary.price_diff_v2_minus_v1 as Dict | undefined)?.p50 as number) ?? null,
                6
              )}
            </p>
            <p className="muted">
              Liquidez: top-of-book no garantiza; ver by_size en análisis. Sin botón de trading.
            </p>
          </>
        ) : (
          <p className="muted">
            Aún sin experimento AM en disco ({String(experiment?.reason || "pendiente")}).
          </p>
        )}
      </section>

      <section className="panel">
        <h3>Captura experimental (acotada ≤30s UI)</h3>
        <p className="muted">
          Plan corto: {String((capturePlan?.plan as Dict | undefined)?.max_seconds ?? "—")}s ·
          est. bytes: {String(disk.estimated_bytes ?? "—")} · 24/7:{" "}
          {String(capturePlan?.permanent_24_7)} · activa: {String(status?.capture_active)}
        </p>
        {captureRun ? (
          <p>
            Eventos: {String(captureRun.n_events)} · duplicados: {String(captureRun.n_duplicates)} ·
            huecos: {String(captureRun.n_gaps)} · errores: {String(captureRun.n_errors)} ·
            permanente: {String(captureRun.permanent_service)}
          </p>
        ) : (
          <p className="muted">Sin captura corta en esta sesión.</p>
        )}
      </section>

      <section className="panel">
        <h3>Lab SELL histórico (solo lectura)</h3>
        {labAudit?.ok ? (
          <>
            <p>
              Examinados: {String(labAudit.n_sells_examined)} · PROBABLE:{" "}
              {String(labAudit.n_probable)} · CONFIRMADO: {String(labAudit.n_confirmado)} ·
              NO_DET: {String(labAudit.n_no_determinable)}
            </p>
            <p>
              Impacto estimado (no aplicado):{" "}
              {fmtNum(labAudit.estimated_aggregate_undercredit_usdt as number | null, 6)} USDT
            </p>
            <p className="muted">Regularización histórica: no ejecutada en AM.</p>
          </>
        ) : (
          <p className="muted">{String(labAudit?.reason || "Sin auditoría Lab")}</p>
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
