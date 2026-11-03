import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtNum, fmtTime } from "../api";

function pillFor(status?: string) {
  const s = (status || "UNKNOWN").toUpperCase();
  if (s === "OK" || s === "RESOLVED") return "ok";
  if (s === "WARNING" || s === "WARN" || s === "LOCKED" || s === "RUNNING" || s === "PENDING")
    return "warn";
  if (s === "ERROR" || s === "CRITICAL" || s === "INVALID") return "err";
  return "info";
}

export default function ProspectPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [decisions, setDecisions] = useState<Record<string, unknown>[]>([]);
  const [audit, setAudit] = useState<Record<string, unknown> | null>(null);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("SHADOW_LIVE");
  const [statusFilter, setStatusFilter] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");
  const [resultActionFilter, setResultActionFilter] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, d, a, r] = await Promise.all([
        api.prospectStatus(),
        api.prospectDecisions(80, {
          experiment_type: typeFilter || undefined,
          status: statusFilter || undefined,
          symbol: symbolFilter || undefined,
          strategy: strategyFilter || undefined,
        }),
        api.prospectAudit(),
        api.prospectReport(typeFilter || "SHADOW_LIVE"),
      ]);
      setStatus(s);
      setDecisions(d);
      setAudit(a);
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }, [typeFilter, statusFilter, symbolFilter, strategyFilter]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 20000);
    return () => clearInterval(id);
  }, [load]);

  async function runLive() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.prospectShadowLiveRun();
      setMsg(
        `SHADOW_LIVE: ${r.generated} decisiones registradas (inmutables). Sin tocar capital SMA.`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function runResolve() {
    setBusy(true);
    try {
      const r = await api.prospectResolve();
      setMsg(
        `Resolución: ${r.resolved} resueltas, ${r.invalid} inválidas, ${r.still_pending} pendientes.`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function evalAlerts() {
    setBusy(true);
    try {
      const r = await api.prospectAlertsEvaluate();
      setMsg(
        `Alertas: ${(r.opened_or_updated as string[])?.length ?? 0} abiertas/actualizadas.`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function runReconcile() {
    setBusy(true);
    try {
      const r = await api.prospectReconcile();
      setMsg(
        `Reconciliación: críticas=${(r.critical as unknown[])?.length ?? 0}, avisos=${(r.warnings as unknown[])?.length ?? 0}, block_entries=${String(r.block_new_entries)}`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const counts = (status?.counts as Record<string, number>) || {};
  const virt = (status?.virtual_ledger as Record<string, unknown>) || {};
  const byType = (status?.counts_by_type as Record<string, Record<string, number>>) || {};
  const sched = (status?.scheduler as Record<string, unknown>) || {};
  const schedState = (sched.state as Record<string, unknown>) || {};
  const metrics = (status?.metrics_shadow_live as Record<string, unknown>) || {};
  const hypo = (metrics.hypothetical_signals as Record<string, unknown>) || {};
  const portfolio = (metrics.virtual_portfolio as Record<string, unknown>) || {};
  const bySymbol = (metrics.by_symbol as Record<string, unknown>[]) || [];
  const openAlerts = (status?.open_alerts as Record<string, unknown>[]) || [];
  const dataClasses = (status?.data_classes as Record<string, string>) || {};
  const buyCi = (hypo.buy_net_ci as Record<string, unknown>) || {};
  const cycles = (audit?.cycles as Record<string, unknown>[]) || [];
  const recon = (audit?.reconciliation as Record<string, unknown>) || {};
  const horizons = (recon.horizons_pending as Record<string, unknown>[]) || [];
  const paperRecon = (recon.paper_sma as Record<string, unknown>) || {};
  const virtId = ((recon.virtual_ledger as Record<string, unknown>)?.identity ||
    {}) as Record<string, unknown>;
  const reportCounts = (report?.counts as Record<string, number>) || {};
  const reportClass = (report?.classification as Record<string, unknown>) || {};
  const reportProb = (report?.probability_scores as Record<string, unknown>) || {};
  const reportHypo = (report?.hypothetical_buy as Record<string, unknown>) || {};
  const reportDecisions = (report?.decisions as Record<string, unknown>[]) || [];
  const curve = (report?.equity_curve_hypo_buy as Record<string, unknown>[]) || [];
  const filteredResults = useMemo(() => {
    return reportDecisions.filter((d) => {
      if (resultActionFilter && String(d.action) !== resultActionFilter) return false;
      if (statusFilter && String(d.resolution_status) !== statusFilter) return false;
      if (symbolFilter && !String(d.symbol).includes(symbolFilter.toUpperCase())) return false;
      return true;
    });
  }, [reportDecisions, resultActionFilter, statusFilter, symbolFilter]);
  const chartData = curve.map((p, i) => ({
    i: i + 1,
    cum: Number(p.cum_hypo_buy_net),
    label: String(p.symbol),
  }));

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Seguimiento prospectivo</h2>
          <p>
            Shadow scheduler autónomo · decisiones antes del resultado · ledger virtual
            separado del paper SMA · PAPER_AI no autorizado.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void load()} disabled={busy}>
            Actualizar
          </button>
          <button className="btn" onClick={() => void evalAlerts()} disabled={busy}>
            Evaluar deterioro
          </button>
          <button className="btn" onClick={() => void runReconcile()} disabled={busy}>
            Reconciliar
          </button>
          <button className="btn" onClick={() => void runResolve()} disabled={busy}>
            Resolver horizontes
          </button>
          <button className="btn primary" onClick={() => void runLive()} disabled={busy}>
            {busy ? "Ejecutando…" : "Registrar SHADOW_LIVE"}
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {msg && (
        <div className="card" style={{ marginBottom: 14, borderColor: "#2dd4bf" }}>
          {msg}
        </div>
      )}

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Shadow Scheduler</h3>
        <p>
          Salud:{" "}
          <span className={`pill ${pillFor(String(sched.health || "UNKNOWN"))}`}>
            {String(sched.health || "UNKNOWN")}
          </span>{" "}
          · DB status: {String(schedState.status ?? "Sin datos")} · Modelo:{" "}
          {String(sched.active_model_version ?? "Sin datos")}
        </p>
        <p>
          Heartbeat hace {fmtNum(sched.heartbeat_age_s as number | null, 0)} s · Último ciclo:{" "}
          {fmtTime(schedState.last_cycle_at as string)} · Última predicción:{" "}
          {fmtTime(sched.last_prediction_at as string)} · Última resolución:{" "}
          {fmtTime(sched.last_resolve_at as string)}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          Errores inferencia: {String(schedState.inference_errors ?? 0)} · resolución:{" "}
          {String(schedState.resolve_errors ?? 0)} · conexión:{" "}
          {String(schedState.connection_errors ?? 0)} · ciclos:{" "}
          {String(schedState.cycle_count ?? 0)}
          {schedState.last_error ? ` · último error: ${String(schedState.last_error)}` : ""}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          Observado: {dataClasses.observed || "—"} · Simulado: {dataClasses.simulated || "—"}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          Duplicados evitados (ciclos recientes):{" "}
          {String(audit?.duplicates_avoided_recent ?? "UNKNOWN")} · Próxima vela inferencia
          open_ms: {String(audit?.next_candle_open_ms_for_inference ?? "UNKNOWN")} · Retraso
          resolución medio: {fmtNum(audit?.resolution_lag_s_mean as number | null, 0)} s
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Últimos ciclos del scheduler</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Inicio UTC</th>
                <th>Duración s</th>
                <th>OK</th>
                <th>Nuevas</th>
                <th>Skip/dup</th>
                <th>Resueltas</th>
                <th>Inválidas</th>
              </tr>
            </thead>
            <tbody>
              {cycles.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted">
                    UNKNOWN — sin ciclos registrados
                  </td>
                </tr>
              ) : (
                cycles.map((c) => (
                  <tr key={String(c.id)}>
                    <td>{String(c.id)}</td>
                    <td>{fmtTime(c.started_at as string)}</td>
                    <td>{fmtNum(c.duration_s as number | null, 2)}</td>
                    <td>{String(c.ok)}</td>
                    <td>{String(c.decisions_new ?? 0)}</td>
                    <td>{String(c.decisions_skipped ?? 0)}</td>
                    <td>{String(c.resolved ?? 0)}</td>
                    <td>{String(c.invalid ?? 0)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Reconciliación e integridad</h3>
        <p>
          Paper SMA: cash {fmtNum(paperRecon.cash as number | null, 2)} · pos{" "}
          {String(paperRecon.positions ?? "UNKNOWN")} · trades{" "}
          {String(paperRecon.trades ?? "UNKNOWN")} · ok={String(paperRecon.ok ?? "UNKNOWN")}
        </p>
        <p>
          Ledger virtual identity ok={String(virtId.ok ?? "UNKNOWN")} · cash{" "}
          {fmtNum(virtId.cash as number | null, 2)} · block_new_entries=
          {String(recon.block_new_entries ?? "UNKNOWN")}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          Críticas: {JSON.stringify(recon.critical ?? [])} · Avisos:{" "}
          {JSON.stringify(recon.warnings ?? [])}
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Horizontes PENDING (no adelantar)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Símbolo</th>
                <th>Acción</th>
                <th>Vela origen UTC</th>
                <th>Listo tras UTC</th>
                <th>¿Listo?</th>
                <th>Segundos</th>
              </tr>
            </thead>
            <tbody>
              {horizons.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    Sin pendientes
                  </td>
                </tr>
              ) : (
                horizons.map((h) => (
                  <tr key={String(h.id)}>
                    <td>{String(h.id)}</td>
                    <td>{String(h.symbol)}</td>
                    <td>{String(h.action)}</td>
                    <td>{fmtTime(h.candle_open_utc as string)}</td>
                    <td>{fmtTime(h.horizon_ready_after_utc as string)}</td>
                    <td>{String(h.horizon_ready)}</td>
                    <td>{fmtNum(h.seconds_until_ready as number | null, 0)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid stats" style={{ marginBottom: 14 }}>
        <div className="card">
          <div className="stat-label">Pendientes</div>
          <div className="stat-value">{counts.PENDING ?? "Sin datos"}</div>
        </div>
        <div className="card">
          <div className="stat-label">Resueltas</div>
          <div className="stat-value">{counts.RESOLVED ?? "Sin datos"}</div>
        </div>
        <div className="card">
          <div className="stat-label">Inválidas</div>
          <div className="stat-value">{counts.INVALID ?? "Sin datos"}</div>
        </div>
        <div className="card">
          <div className="stat-label">Ledger virtual cash</div>
          <div className="stat-value">{fmtNum(virt.cash as number | null, 2)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Circuit breaker</div>
          <div className="stat-value" style={{ fontSize: 16 }}>
            {(status?.circuit_breaker as { active?: boolean; reason?: string } | null)
              ?.active
              ? `ACTIVO (${(status?.circuit_breaker as { reason?: string }).reason})`
              : "Inactivo"}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Paper SMA</div>
          <div className="stat-value" style={{ fontSize: 16 }}>
            {status?.paper_sma_untouched ? "No mezclado" : "Revisar"}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Informe prospectivo SHADOW_LIVE</h3>
        <p>
          Total: {String(reportCounts.total ?? counts.total ?? "UNKNOWN")} · Pendientes:{" "}
          {String(reportCounts.pending ?? counts.PENDING ?? "UNKNOWN")} · Resueltas:{" "}
          {String(reportCounts.resolved ?? counts.RESOLVED ?? "UNKNOWN")} · Inválidas:{" "}
          {String(reportCounts.invalid ?? counts.INVALID ?? "UNKNOWN")}
        </p>
        <p>
          BUY resueltas: {String(reportCounts.buy_resolved ?? hypo.n_buy ?? 0)} · HOLD
          resueltas (abstención): {String(reportCounts.hold_resolved ?? hypo.n_hold ?? 0)} ·
          HOLD ≠ trade ganador
        </p>
        <p>
          Accuracy BUY: {fmtNum(reportClass.accuracy_buy_directional as number | null, 4)} ·
          Brier:{" "}
          {reportProb.applicable
            ? fmtNum(reportProb.brier as number | null, 4)
            : "N/A"}{" "}
          · LogLoss:{" "}
          {reportProb.applicable
            ? fmtNum(reportProb.logloss as number | null, 4)
            : "N/A"}
        </p>
        <p>
          Media net hipotético BUY: {fmtNum(reportHypo.mean_net as number | null, 5)} · vs
          cash: {fmtNum(reportHypo.vs_cash as number | null, 5)} · IC bootstrap: [
          {fmtNum(buyCi.low as number | null, 5)}, {fmtNum(buyCi.high as number | null, 5)}]
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          {String(
            report?.evidence_label ||
              portfolio.evidence_label ||
              portfolio.warning ||
              "Evidencia insuficiente"
          )}{" "}
          · {String(report?.portfolio_pnl_note || "")}
        </p>
        {bySymbol.length > 0 && (
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Símbolo</th>
                  <th>BUY</th>
                  <th>HOLD</th>
                  <th>Media net BUY</th>
                </tr>
              </thead>
              <tbody>
                {bySymbol.map((r) => (
                  <tr key={String(r.symbol)}>
                    <td>{String(r.symbol)}</td>
                    <td>{String(r.buys)}</td>
                    <td>{String(r.holds)}</td>
                    <td>{fmtNum(r.mean_buy_net as number | null, 5)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Evolución hipotética acumulada (solo BUY resueltas)</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          No es PnL de cartera financiada. HOLD excluido. Sin puntos = evidencia insuficiente.
        </p>
        {chartData.length === 0 ? (
          <p>Evidencia insuficiente — sin BUY resueltas aún.</p>
        ) : (
          <div style={{ width: "100%", height: 220 }}>
            <ResponsiveContainer>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="i" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="cum"
                  name="cum_hypo_buy_net"
                  stroke="#2dd4bf"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Tabla de resultados prospectivos</h3>
        <div className="actions" style={{ gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
          <select
            value={resultActionFilter}
            onChange={(e) => setResultActionFilter(e.target.value)}
          >
            <option value="">BUY y HOLD</option>
            <option value="BUY">BUY</option>
            <option value="HOLD">HOLD</option>
          </select>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Señal</th>
                <th>Símbolo</th>
                <th>Acción</th>
                <th>Prob.</th>
                <th>Px entrada</th>
                <th>Px salida</th>
                <th>Ret. activo</th>
                <th>Net hipot. BUY</th>
                <th>Clasif.</th>
                <th>Calidad</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {filteredResults.length === 0 ? (
                <tr>
                  <td colSpan={11} className="muted">
                    Sin filas (horizontes aún pendientes o filtros vacíos).
                  </td>
                </tr>
              ) : (
                filteredResults.map((d) => (
                  <tr key={String(d.id)}>
                    <td>{fmtTime(d.signal_ts as string)}</td>
                    <td>{String(d.symbol)}</td>
                    <td>{String(d.action)}</td>
                    <td>
                      {d.probability == null
                        ? "N/A"
                        : fmtNum(d.probability as number, 3)}
                    </td>
                    <td>{fmtNum(d.entry_price_observed as number | null, 4)}</td>
                    <td>
                      {d.exit_price_observed == null
                        ? "—"
                        : fmtNum(d.exit_price_observed as number, 4)}
                    </td>
                    <td>
                      {d.asset_return == null
                        ? "—"
                        : fmtNum(d.asset_return as number, 5)}
                    </td>
                    <td>
                      {d.action === "HOLD"
                        ? "abstención"
                        : d.hypothetical_net_if_buy == null
                          ? "—"
                          : fmtNum(d.hypothetical_net_if_buy as number, 5)}
                    </td>
                    <td>
                      {d.classification_hit == null
                        ? "—"
                        : d.classification_hit
                          ? "hit"
                          : "miss"}
                    </td>
                    <td>{String(d.data_quality ?? "—")}</td>
                    <td>
                      <span className={`pill ${pillFor(String(d.resolution_status))}`}>
                        {String(d.resolution_status)}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Alertas de deterioro</h3>
        {openAlerts.length === 0 ? (
          <p className="muted">Sin alertas abiertas.</p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Severidad</th>
                  <th>Código</th>
                  <th>Mensaje</th>
                  <th>Creada</th>
                </tr>
              </thead>
              <tbody>
                {openAlerts.map((a) => (
                  <tr key={String(a.id)}>
                    <td>
                      <span className={`pill ${pillFor(String(a.severity))}`}>
                        {String(a.severity)}
                      </span>
                    </td>
                    <td>{String(a.code)}</td>
                    <td>{String(a.message)}</td>
                    <td>{fmtTime(a.created_at as string)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Tipos de experimento (no mezclar métricas)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Pendientes</th>
                <th>Resueltas</th>
                <th>Inválidas</th>
              </tr>
            </thead>
            <tbody>
              {["BACKTEST", "SHADOW_REPLAY", "SHADOW_LIVE", "PAPER_TRADE"].map((t) => (
                <tr key={t}>
                  <td>{t}</td>
                  <td>{byType[t]?.PENDING ?? 0}</td>
                  <td>{byType[t]?.RESOLVED ?? 0}</td>
                  <td>{byType[t]?.INVALID ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Filtros</h3>
        <div className="actions" style={{ gap: 8, flexWrap: "wrap" }}>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">Todos los tipos</option>
            <option value="SHADOW_LIVE">SHADOW_LIVE</option>
            <option value="SHADOW_REPLAY">SHADOW_REPLAY</option>
            <option value="BACKTEST">BACKTEST</option>
            <option value="PAPER_TRADE">PAPER_TRADE</option>
          </select>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">Todos los estados</option>
            <option value="PENDING">PENDING</option>
            <option value="RESOLVED">RESOLVED</option>
            <option value="INVALID">INVALID</option>
          </select>
          <input
            placeholder="Símbolo"
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
          />
          <input
            placeholder="Estrategia"
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value)}
          />
          <button className="btn" onClick={() => void load()}>
            Aplicar
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Decisiones (inmutables)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Tipo</th>
                <th>Símbolo</th>
                <th>Acción</th>
                <th>Motivo</th>
                <th>Estado</th>
                <th>Net obs.</th>
                <th>Calidad</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted">
                    Sin decisiones aún (el scheduler las registrará en el próximo ciclo).
                  </td>
                </tr>
              ) : (
                decisions.map((d) => (
                  <tr key={String(d.id)}>
                    <td>{fmtTime(d.created_at as string)}</td>
                    <td>{String(d.experiment_type)}</td>
                    <td>{String(d.symbol)}</td>
                    <td>{String(d.action)}</td>
                    <td>{String(d.reason)}</td>
                    <td>{String(d.resolution_status)}</td>
                    <td>
                      {d.observed_net_return == null
                        ? "—"
                        : fmtNum(d.observed_net_return as number, 5)}
                    </td>
                    <td>{String(d.outcome_quality ?? "—")}</td>
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
