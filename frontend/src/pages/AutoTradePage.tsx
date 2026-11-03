import { useCallback, useEffect, useState } from "react";
import { api, fmtNum, fmtTime } from "../api";

function pillFor(status?: string) {
  const s = (status || "UNKNOWN").toUpperCase();
  if (s === "OK" || s === "FILLED") return "ok";
  if (s === "WARNING" || s === "PAUSED" || s === "NEW" || s === "VALIDATED") return "warn";
  if (s === "ERROR" || s === "REJECTED" || s === "CRITICAL") return "err";
  return "info";
}

const LAB_TOKEN = "paper";

export default function AutoTradePage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

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

  async function pause() {
    setBusy(true);
    try {
      await api.labPause(LAB_TOKEN);
      setMsg("Ejecutor pausado.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function resume() {
    setBusy(true);
    try {
      await api.labResume(LAB_TOKEN);
      setMsg("Ejecutor reanudado (órdenes pendientes no se disparan solas).");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function cycle() {
    setBusy(true);
    try {
      const r = await api.labCycle(LAB_TOKEN);
      setMsg(
        `Ciclo lab: filled=${(r.orders as { filled?: number })?.filled ?? 0}, rejected=${(r.orders as { rejected?: number })?.rejected ?? 0}, signals_enq=${(r.signals as { enqueued?: number })?.enqueued ?? 0}`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const exec = (status?.executor as Record<string, unknown>) || {};
  const eq = (status?.equity as Record<string, unknown>) || {};
  const counts = (status?.counts as Record<string, number>) || {};
  const integrity = (status?.integrity as Record<string, unknown>) || {};
  const sma = (integrity.sma_paper as Record<string, unknown>) || {};
  const positions = (status?.positions as Record<string, unknown>[]) || [];
  const pending = (status?.orders_pending as Record<string, unknown>[]) || [];
  const rejected = (status?.orders_rejected as Record<string, unknown>[]) || [];
  const trades = (status?.trades as Record<string, unknown>[]) || [];

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Trading Automático</h2>
          <p>
            Motor lab PAPER_ONLY · ledger aislado (no SMA histórico ni Shadow) · estrategia
            autorizada SMA10/50 · sin órdenes reales.
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
          <div className="stat-label">Cash lab</div>
          <div className="stat-value">{fmtNum(eq.cash as number | null, 2)}</div>
        </div>
        <div className="card">
          <div className="stat-label">P/L realizado</div>
          <div className="stat-value">
            {fmtNum(status?.realized_pnl as number | null, 4)}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Estado operativo</h3>
        <p>
          Compras: {counts.buys ?? 0} · Ventas: {counts.sells ?? 0} · Pendientes:{" "}
          {counts.pending_orders ?? 0} · Rechazadas: {counts.rejected_orders ?? 0} ·
          Comisiones sim: {fmtNum(status?.fees_simulated as number | null, 4)}
        </p>
        <p>
          Heartbeat: {fmtTime(exec.heartbeat_at as string)} · Ciclos:{" "}
          {String(exec.cycle_count ?? 0)} · Posiciones: {String(eq.positions_n ?? 0)}
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          SMA histórico intacto: cash {fmtNum(sma.cash as number | null, 2)} · pos{" "}
          {String(sma.positions ?? "—")} · trades {String(sma.trades ?? "—")} · research_sim:{" "}
          {fmtNum(integrity.research_sim_cash as number | null, 2)} · Shadow no ejecuta.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Posiciones lab abiertas</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Símbolo</th>
                <th>Qty</th>
                <th>Coste</th>
                <th>Entrada</th>
                <th>SL%</th>
                <th>TP%</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    Sin posiciones lab
                  </td>
                </tr>
              ) : (
                positions.map((p) => (
                  <tr key={String(p.symbol)}>
                    <td>{String(p.symbol)}</td>
                    <td>{fmtNum(p.qty as number, 6)}</td>
                    <td>{fmtNum(p.cost as number, 2)}</td>
                    <td>{fmtNum(p.entry_price as number | null, 4)}</td>
                    <td>{fmtNum(p.stop_loss_pct as number | null, 3)}</td>
                    <td>{fmtNum(p.take_profit_pct as number | null, 3)}</td>
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
        <h3>Trades lab (compras/ventas virtuales)</h3>
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
                    Sin trades lab aún (esperar cruce SMA o ciclo manual).
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
