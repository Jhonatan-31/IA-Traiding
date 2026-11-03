import { useCallback, useEffect, useState } from "react";
import { api, fmtNum, fmtTime } from "../api";

function pillFor(status?: string) {
  const s = (status || "UNKNOWN").toUpperCase();
  if (s === "OK" || s === "FILLED") return "ok";
  if (s === "WARNING" || s === "PAUSED" || s === "NEW" || s === "VALIDATED" || s === "INCOMPLETE")
    return "warn";
  if (s === "ERROR" || s === "REJECTED" || s === "CRITICAL") return "err";
  return "info";
}

const TOKEN_KEY = "lab_control_token";

export default function AutoTradePage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");

  const load = useCallback(async () => {
    setError(null);
    try {
      setStatus(await api.labStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 15000);
    return () => clearInterval(id);
  }, [load]);

  function saveToken(v: string) {
    setToken(v);
    if (v) sessionStorage.setItem(TOKEN_KEY, v);
    else sessionStorage.removeItem(TOKEN_KEY);
  }

  function requireToken(): string | null {
    if (!token.trim()) {
      setError("Configure el token de control (LAB_CONTROL_TOKEN) antes de pausar/reanudar/ciclo.");
      return null;
    }
    return token.trim();
  }

  async function pause() {
    const t = requireToken();
    if (!t) return;
    setBusy(true);
    try {
      await api.labPause(t);
      setMsg("Ejecutor pausado.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function resume() {
    const t = requireToken();
    if (!t) return;
    setBusy(true);
    try {
      await api.labResume(t);
      setMsg("Ejecutor reanudado (sin auto-disparo de pendientes).");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function cycle() {
    const t = requireToken();
    if (!t) return;
    setBusy(true);
    try {
      const r = await api.labCycle(t);
      const sig = (r.signals as Record<string, number>) || {};
      setMsg(
        `Ciclo: buy=${sig.signals_buy ?? 0} sell=${sig.signals_sell ?? 0} hold=${sig.signals_hold ?? 0} · filled=${(r.orders as { filled?: number })?.filled ?? 0} · rejected=${(r.orders as { rejected?: number })?.rejected ?? 0} · ${r.duration_ms ?? "?"} ms`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const exec = (status?.executor as Record<string, unknown>) || {};
  const val = (status?.valuation as Record<string, unknown>) || {};
  const counts = (status?.counts as Record<string, number>) || {};
  const integrity = (status?.integrity as Record<string, unknown>) || {};
  const sma = (integrity.sma_paper as Record<string, unknown>) || {};
  const positions = (status?.positions as Record<string, unknown>[]) || [];
  const pending = (status?.orders_pending as Record<string, unknown>[]) || [];
  const rejected = (status?.orders_rejected as Record<string, unknown>[]) || [];
  const trades = (status?.trades as Record<string, unknown>[]) || [];
  const cycles = (status?.cycles as Record<string, unknown>[]) || [];
  const alerts = (status?.alerts as Record<string, unknown>[]) || [];
  const lastCycle = (status?.last_cycle as Record<string, unknown>) || {};
  const obs = (status?.observability as Record<string, unknown>) || {};
  const decisions = (obs.decisions_24h as Record<string, number>) || {};
  const equityHist = (status?.equity_history as Record<string, unknown>[]) || [];
  const evals = (status?.signal_evals_recent as Record<string, unknown>[]) || [];
  const organic = (status?.organic_signals as Record<string, unknown>[]) || [];
  const sellHistory = (status?.sell_history as Record<string, unknown>[]) || [];
  const exitPolicy = (status?.exit_policy as Record<string, unknown>) || {};

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Trading Automático</h2>
          <p>
            Motor lab PAPER_ONLY · ledger aislado · SMA10/50 autorizada · token de control
            obligatorio · sin órdenes reales.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void load()} disabled={busy}>
            Actualizar
          </button>
          <button className="btn" onClick={() => void pause()} disabled={busy}>
            Pausar
          </button>
          <button className="btn" onClick={() => void resume()} disabled={busy}>
            Reanudar
          </button>
          <button className="btn primary" onClick={() => void cycle()} disabled={busy}>
            {busy ? "Ejecutando…" : "Ciclo manual"}
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
        <h3>Token de control</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Debe coincidir con LAB_CONTROL_TOKEN del entorno. No se envía a logs. Solo en
          sessionStorage del navegador.
        </p>
        <input
          type="password"
          placeholder="LAB_CONTROL_TOKEN"
          value={token}
          onChange={(e) => saveToken(e.target.value)}
          style={{ width: "min(420px, 100%)" }}
        />
      </div>

      {alerts.length > 0 && (
        <div className="card" style={{ marginBottom: 14, borderColor: "#f59e0b" }}>
          <h3>Alertas</h3>
          {alerts.map((a, i) => (
            <p key={i}>
              <span className={`pill ${pillFor(String(a.severity))}`}>{String(a.severity)}</span>{" "}
              {String(a.code)} — {String(a.message)}
            </p>
          ))}
        </div>
      )}

      <div className="grid stats" style={{ marginBottom: 14 }}>
        <div className="card">
          <div className="stat-label">Modo</div>
          <div className="stat-value" style={{ fontSize: 18 }}>
            {String(status?.mode || "PAPER_ONLY")}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Ejecutor</div>
          <div style={{ marginTop: 8 }}>
            <span className={`pill ${pillFor(String(exec.status || "UNKNOWN"))}`}>
              {String(exec.status || "UNKNOWN")}
            </span>
            {exec.paused ? " · PAUSADO" : ""}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Estrategia</div>
          <div className="stat-value" style={{ fontSize: 16 }}>
            {String(status?.authorized_strategy || "UNKNOWN")}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Circuit breaker</div>
          <div className="stat-value" style={{ fontSize: 16 }}>
            {exec.breaker_active
              ? `ACTIVO (${String(exec.breaker_reason)})`
              : "Inactivo"}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Cash / Patrimonio</div>
          <div className="stat-value" style={{ fontSize: 18 }}>
            {fmtNum(val.cash as number | null, 2)} /{" "}
            {val.equity_estimate == null
              ? "INCOMPLETO"
              : fmtNum(val.equity_estimate as number, 2)}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">P/L real. / no real.</div>
          <div className="stat-value" style={{ fontSize: 18 }}>
            {fmtNum(val.realized_pnl as number | null, 4)} /{" "}
            {val.unrealized_pnl == null
              ? "—"
              : fmtNum(val.unrealized_pnl as number, 4)}
          </div>
        </div>
      </div>

      {obs.operating_without_opportunity ? (
        <div className="card" style={{ marginBottom: 14, borderColor: "#2dd4bf" }}>
          Sistema operativo sin oportunidades: sin cruces SMA en el último ciclo (HOLD). No se
          fuerzan operaciones.
        </div>
      ) : null}

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Observabilidad</h3>
        <p>
          Ciclos/hora: {String(obs.cycles_last_hour ?? 0)} · Evaluaciones 24h:{" "}
          {String(obs.signals_evaluated_24h ?? 0)} · Cruces:{" "}
          {String(obs.crosses_detected_24h ?? 0)} · BUY/SELL/HOLD:{" "}
          {String(decisions.buy ?? 0)}/{String(decisions.sell ?? 0)}/{String(decisions.hold ?? 0)}
        </p>
        <p>
          Órdenes aceptadas: {String(obs.orders_accepted ?? 0)} · rechazadas:{" "}
          {String(obs.orders_rejected ?? 0)} · Fees:{" "}
          {fmtNum(obs.fees_accumulated as number | null, 4)} · Slippage est.:{" "}
          {fmtNum(obs.slippage_estimated as number | null, 4)} · Breaker:{" "}
          {obs.circuit_breaker_active ? "ACTIVO" : "inactivo"}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          Última vela procesada (open_ms): {String(obs.last_candle_ms ?? "—")}
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Valoración mark-to-market</h3>
        <p>
          Estado:{" "}
          <span className={`pill ${pillFor(String(val.valuation_status || "UNKNOWN"))}`}>
            {String(val.valuation_status || "UNKNOWN")}
          </span>{" "}
          · MV posiciones: {fmtNum(val.market_value_positions as number | null, 2)} · Fees:{" "}
          {fmtNum(val.fees_accumulated as number | null, 4)} · Retorno vs inicial:{" "}
          {fmtNum(val.return_vs_initial as number | null, 4)} · DD vs peak:{" "}
          {fmtNum(val.drawdown_vs_peak as number | null, 6)} (
          {val.drawdown_vs_peak_pct == null
            ? "—"
            : fmtNum(val.drawdown_vs_peak_pct as number, 4)}
          %) · peak {fmtNum(val.peak_equity as number | null, 2)}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          {String(val.note || "")}
        </p>
        <p>
          Último ciclo: {fmtTime(lastCycle.finished_at as string)} · scanned={" "}
          {String(lastCycle.symbols_scanned ?? "—")} · BUY/SELL/HOLD={" "}
          {String(lastCycle.signals_buy ?? 0)}/{String(lastCycle.signals_sell ?? 0)}/
          {String(lastCycle.signals_hold ?? 0)} · gen/rej/fill={" "}
          {String(lastCycle.orders_generated ?? 0)}/{String(lastCycle.orders_rejected ?? 0)}/
          {String(lastCycle.orders_filled ?? 0)} · {String(lastCycle.duration_ms ?? "—")} ms
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          SMA histórico: cash {fmtNum(sma.cash as number | null, 2)} · pos{" "}
          {String(sma.positions ?? "—")} · trades {String(sma.trades ?? "—")} · research_sim:{" "}
          {fmtNum(integrity.research_sim_cash as number | null, 2)} · lab cash:{" "}
          {fmtNum(integrity.lab_cash as number | null, 2)}
        </p>
        <p>
          Operaciones: compras {counts.buys ?? 0} · ventas {counts.sells ?? 0} · pendientes{" "}
          {counts.pending_orders ?? 0} · rechazadas {counts.rejected_orders ?? 0}
        </p>
        {exec.last_error ? (
          <p className="muted" style={{ fontSize: 12 }}>
            Último error ejecutor: {String(exec.last_error)}
          </p>
        ) : null}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Historial capital virtual</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Día</th>
                <th>Inicio</th>
                <th>Fin</th>
              </tr>
            </thead>
            <tbody>
              {equityHist.length === 0 ? (
                <tr>
                  <td colSpan={3} className="muted">
                    Sin series diarias aún
                  </td>
                </tr>
              ) : (
                equityHist.map((e) => (
                  <tr key={String(e.day)}>
                    <td>{String(e.day)}</td>
                    <td>{fmtNum(e.start_equity as number, 2)}</td>
                    <td>
                      {e.end_equity == null ? "—" : fmtNum(e.end_equity as number, 2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Auditoría de señales (evaluaciones)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>UTC</th>
                <th>Símbolo</th>
                <th>Vela</th>
                <th>SMA10</th>
                <th>SMA50</th>
                <th>Cruce</th>
                <th>Decisión</th>
                <th>Motivo</th>
                <th>Datos</th>
                <th>Riesgo</th>
              </tr>
            </thead>
            <tbody>
              {evals.length === 0 ? (
                <tr>
                  <td colSpan={10} className="muted">
                    Sin evaluaciones registradas aún
                  </td>
                </tr>
              ) : (
                evals.slice(0, 25).map((e, i) => (
                  <tr key={`${String(e.symbol)}-${String(e.at)}-${i}`}>
                    <td>{fmtTime(e.at as string)}</td>
                    <td>{String(e.symbol)}</td>
                    <td>{String(e.candle_ms ?? "—")}</td>
                    <td>
                      {e.sma10 == null ? "—" : fmtNum(e.sma10 as number, 4)}
                    </td>
                    <td>
                      {e.sma50 == null ? "—" : fmtNum(e.sma50 as number, 4)}
                    </td>
                    <td>{String(e.cross_state ?? "—")}</td>
                    <td>{String(e.decision)}</td>
                    <td>{String(e.reason ?? "—")}</td>
                    <td>{String(e.data_status ?? "—")}</td>
                    <td>{String(e.risk_status ?? "—")}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Señales orgánicas persistidas</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>UTC</th>
                <th>Side</th>
                <th>Símbolo</th>
                <th>Vela</th>
                <th>Ref</th>
              </tr>
            </thead>
            <tbody>
              {organic.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    Sin cruces persistidos
                  </td>
                </tr>
              ) : (
                organic.map((s) => (
                  <tr key={String(s.id)}>
                    <td>{String(s.id)}</td>
                    <td>{fmtTime(s.created_at as string)}</td>
                    <td>{String(s.side)}</td>
                    <td>{String(s.symbol)}</td>
                    <td>{String(s.candle_ms)}</td>
                    <td>{fmtNum(s.ref_price as number, 4)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Ciclos orgánicos recientes</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>ID</th>
                <th>Fin UTC</th>
                <th>ms</th>
                <th>Scan</th>
                <th>BUY</th>
                <th>SELL</th>
                <th>HOLD</th>
                <th>Gen</th>
                <th>Rej</th>
                <th>Fill</th>
                <th>Err</th>
              </tr>
            </thead>
            <tbody>
              {cycles.length === 0 ? (
                <tr>
                  <td colSpan={11} className="muted">
                    Sin ciclos registrados aún
                  </td>
                </tr>
              ) : (
                cycles.map((c) => (
                  <tr key={String(c.id)}>
                    <td>{String(c.id)}</td>
                    <td>{fmtTime(c.finished_at as string)}</td>
                    <td>{String(c.duration_ms ?? "—")}</td>
                    <td>{String(c.symbols_scanned ?? 0)}</td>
                    <td>{String(c.signals_buy ?? 0)}</td>
                    <td>{String(c.signals_sell ?? 0)}</td>
                    <td>{String(c.signals_hold ?? 0)}</td>
                    <td>{String(c.orders_generated ?? 0)}</td>
                    <td>{String(c.orders_rejected ?? 0)}</td>
                    <td>{String(c.orders_filled ?? 0)}</td>
                    <td>{String(c.errors ?? 0)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Posiciones abiertas y salidas</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Política: SL {(Number(exitPolicy.stop_loss_pct) * 100 || 2).toFixed(0)}% · TP{" "}
          {(Number(exitPolicy.take_profit_pct) * 100 || 4).toFixed(0)}% · max{" "}
          {String(exitPolicy.max_hold_bars ?? 48)} barras · prioridad{" "}
          {Array.isArray(exitPolicy.priority)
            ? (exitPolicy.priority as string[]).join(" → ")
            : "SL → TP → time → SMA"}
          . Mark observado ≠ ejecución simulada (slip).
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Símbolo</th>
                <th>Qty</th>
                <th>Entrada</th>
                <th>Mark obs.</th>
                <th>Exec. est.</th>
                <th>SL</th>
                <th>TP</th>
                <th>Barras rest.</th>
                <th>Coste</th>
                <th>uPnL</th>
                <th>Datos</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={11} className="muted">
                    Sin posiciones lab
                  </td>
                </tr>
              ) : (
                positions.map((p) => (
                  <tr key={String(p.symbol)}>
                    <td>{String(p.symbol)}</td>
                    <td>{fmtNum(p.qty as number, 6)}</td>
                    <td>{fmtNum(p.entry_price as number, 4)}</td>
                    <td>
                      {(p.mark_price_observed ?? p.mark_price) == null
                        ? "—"
                        : fmtNum(
                            (p.mark_price_observed ?? p.mark_price) as number,
                            4
                          )}
                    </td>
                    <td>
                      {p.estimated_sell_execution_price == null
                        ? "—"
                        : fmtNum(p.estimated_sell_execution_price as number, 4)}
                    </td>
                    <td>
                      {p.stop_loss_price == null
                        ? "—"
                        : fmtNum(p.stop_loss_price as number, 4)}
                    </td>
                    <td>
                      {p.take_profit_price == null
                        ? "—"
                        : fmtNum(p.take_profit_price as number, 4)}
                    </td>
                    <td>{String(p.bars_remaining ?? "—")}</td>
                    <td>{fmtNum(p.cost as number, 2)}</td>
                    <td>
                      {p.unrealized_pnl == null
                        ? "—"
                        : fmtNum(p.unrealized_pnl as number, 4)}
                    </td>
                    <td>{String(p.data_status ?? "—")}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <p>
          Patrimonio est.:{" "}
          {val.equity_estimate == null
            ? "INCOMPLETO"
            : fmtNum(val.equity_estimate as number, 2)}{" "}
          · P/L realizado: {fmtNum(val.realized_pnl as number | null, 4)} · Fees:{" "}
          {fmtNum(val.fees_accumulated as number | null, 4)}
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Historial de ventas (cierres)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>UTC</th>
                <th>Símbolo</th>
                <th>Qty</th>
                <th>Precio exec.</th>
                <th>Fee</th>
                <th>Slip</th>
                <th>Motivo</th>
                <th>PnL real.</th>
              </tr>
            </thead>
            <tbody>
              {sellHistory.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted">
                    Sin ventas lab registradas
                  </td>
                </tr>
              ) : (
                sellHistory.map((s) => (
                  <tr key={String(s.id)}>
                    <td>{fmtTime(s.at as string)}</td>
                    <td>{String(s.symbol)}</td>
                    <td>{fmtNum(s.qty as number, 6)}</td>
                    <td>{fmtNum(s.price as number, 4)}</td>
                    <td>{fmtNum(s.fee as number, 4)}</td>
                    <td>{fmtNum(s.slip as number, 4)}</td>
                    <td>{String(s.reason || "—")}</td>
                    <td>
                      {s.realized_pnl == null
                        ? "—"
                        : fmtNum(s.realized_pnl as number, 4)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Órdenes pendientes</h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Side</th>
                  <th>Símbolo</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {pending.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="muted">
                      Ninguna
                    </td>
                  </tr>
                ) : (
                  pending.map((o) => (
                    <tr key={String(o.id)}>
                      <td>{String(o.id)}</td>
                      <td>{String(o.side)}</td>
                      <td>{String(o.symbol)}</td>
                      <td>
                        <span className={`pill ${pillFor(String(o.status))}`}>
                          {String(o.status)}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <h3>Órdenes rechazadas</h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Side</th>
                  <th>Símbolo</th>
                  <th>Motivo</th>
                </tr>
              </thead>
              <tbody>
                {rejected.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="muted">
                      Ninguna
                    </td>
                  </tr>
                ) : (
                  rejected.map((o) => (
                    <tr key={String(o.id)}>
                      <td>{String(o.id)}</td>
                      <td>{String(o.side)}</td>
                      <td>{String(o.symbol)}</td>
                      <td>{String(o.reject_reason || "—")}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Trades lab</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Side</th>
                <th>Símbolo</th>
                <th>Qty</th>
                <th>Precio</th>
                <th>Fee</th>
                <th>Motivo</th>
                <th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted">
                    Sin trades lab
                  </td>
                </tr>
              ) : (
                trades.map((t) => (
                  <tr key={String(t.id)}>
                    <td>{fmtTime(t.at as string)}</td>
                    <td>{String(t.side)}</td>
                    <td>{String(t.symbol)}</td>
                    <td>{fmtNum(t.qty as number, 6)}</td>
                    <td>{fmtNum(t.price as number, 4)}</td>
                    <td>{fmtNum(t.fee as number, 4)}</td>
                    <td>{String(t.reason || "—")}</td>
                    <td>
                      {t.realized_pnl == null
                        ? "—"
                        : fmtNum(t.realized_pnl as number, 4)}
                    </td>
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
