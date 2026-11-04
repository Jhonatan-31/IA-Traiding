import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fmtNum, fmtTime } from "../api";

const TOKEN_KEY = "lab_control_token";

export default function DemoAutoPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [fills, setFills] = useState<Array<Record<string, unknown>>>([]);
  const [decisions, setDecisions] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterAction, setFilterAction] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, f, d] = await Promise.all([
        api.demoStatus(),
        api.demoFills(80, filterSymbol || undefined),
        api.demoDecisions(80, filterSymbol || undefined, filterAction || undefined),
      ]);
      setStatus(s);
      setFills(f);
      setDecisions(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }, [filterSymbol, filterAction]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [load]);

  function saveToken(v: string) {
    setToken(v);
    if (v) sessionStorage.setItem(TOKEN_KEY, v);
    else sessionStorage.removeItem(TOKEN_KEY);
  }

  async function start() {
    if (!token.trim()) {
      setError("Configure LAB_CONTROL_TOKEN (mismo token Lab) para INICIAR/DETENER.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.demoStart(token.trim());
      setMsg(r.changed ? "Bot DEMO en RUNNING." : `Sin cambio: ${String(r.note || r.status)}`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    if (!token.trim()) {
      setError("Configure LAB_CONTROL_TOKEN para DETENER.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.demoStop(token.trim());
      setMsg(
        r.changed
          ? "Bot DETENIDO. Sin nuevas compras; protecciones SL/TP activas."
          : `Sin cambio: ${String(r.note || r.status)}`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const bot = String(status?.bot_status || "—");
  const st = (status?.state as Record<string, unknown>) || {};
  const positions = (status?.positions as Array<Record<string, unknown>>) || [];
  const dc = (status?.decision_counts as Record<string, number>) || {};
  const tc = (status?.trade_counts as Record<string, number>) || {};

  const historyRows = useMemo(() => {
    const rows: Array<Record<string, unknown>> = [];
    for (const t of fills) {
      rows.push({
        kind: "FILL",
        at: t.at,
        symbol: t.symbol,
        action: t.side,
        qty: t.qty,
        price: t.price,
        reason: t.reason,
        fee: t.fee,
        pnl: t.realized_pnl,
        state: "FILLED",
        id: `f-${t.id}`,
      });
    }
    for (const d of decisions) {
      if (d.executed) continue;
      rows.push({
        kind: "SIGNAL",
        at: d.at,
        symbol: d.symbol,
        action: d.action,
        qty: null,
        price: d.observed_price,
        reason: d.reason,
        fee: null,
        pnl: null,
        state: d.executed ? "EXECUTED" : "SIGNAL_ONLY",
        id: `d-${d.id}`,
        score: d.signal_score,
      });
    }
    return rows
      .sort((a, b) => String(b.at).localeCompare(String(a.at)))
      .slice(0, 60);
  }, [fills, decisions]);

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Trading Automático DEMO</h2>
          <p>
            Ledger aislado <code>demo_manual_control</code> · 1000 USDT · política v1 (4/5) ·
            PAPER_ONLY · tú decides INICIAR/DETENER
          </p>
        </div>
        <span className={bot === "RUNNING" ? "pill ok" : "pill warn"}>{bot}</span>
      </div>

      {error && <div className="error-box">{error}</div>}
      {msg && <p className="muted">{msg}</p>}

      <div className="card" style={{ marginBottom: 14 }}>
        <label className="muted" style={{ fontSize: 12 }}>
          Token de control (LAB_CONTROL_TOKEN)
        </label>
        <input
          type="password"
          value={token}
          onChange={(e) => saveToken(e.target.value)}
          style={{ width: "100%", maxWidth: 420, display: "block", marginBottom: 10 }}
          placeholder="No se guarda en el servidor; solo sesión"
        />
        <button className="btn" disabled={busy || bot === "RUNNING"} onClick={() => void start()}>
          INICIAR BOT
        </button>{" "}
        <button className="btn" disabled={busy || bot === "STOPPED"} onClick={() => void stop()}>
          DETENER BOT
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))",
          gap: 12,
          marginBottom: 14,
        }}
      >
        <div className="card">
          <h3>Estado</h3>
          <p>Bot: {bot}</p>
          <p>Conexión: {String(st.connection_ok ?? "—")}</p>
          <p>Última eval: {fmtTime(st.last_eval_at as string)}</p>
          <p>Próxima: {fmtTime(st.next_eval_at as string)}</p>
          <p>Heartbeat: {fmtTime(st.heartbeat_at as string)}</p>
          <p>Ciclos: {String(st.cycle_count ?? 0)}</p>
        </div>
        <div className="card">
          <h3>Patrimonio</h3>
          <p>Equity: {fmtNum(status?.equity as number, 2)}</p>
          <p>Cash: {fmtNum(status?.cash as number, 2)}</p>
          <p>rPnL: {fmtNum(status?.realized_pnl as number, 4)}</p>
          <p>uPnL: {fmtNum(status?.unrealized_pnl as number, 4)}</p>
          <p>DD vs peak: {fmtNum(status?.drawdown_vs_peak as number, 6)}</p>
        </div>
        <div className="card">
          <h3>Actividad</h3>
          <p>
            Señales B/S/H: {dc.BUY ?? 0}/{dc.SELL ?? 0}/{dc.HOLD ?? 0}
          </p>
          <p>
            Fills compra/venta: {tc.buys ?? 0}/{tc.sells ?? 0}
          </p>
          <p>Ejecutadas (decisions.executed): {dc.executed ?? 0}</p>
          <p className="muted" style={{ fontSize: 12 }}>
            probability_validated=false · score ≠ probabilidad
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Posiciones</h3>
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

      <div className="card">
        <h3>Historial (fills + señales no ejecutadas)</h3>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <select value={filterSymbol} onChange={(e) => setFilterSymbol(e.target.value)}>
            <option value="">Todos símbolos</option>
            <option value="BTCUSDT">BTCUSDT</option>
            <option value="ETHUSDT">ETHUSDT</option>
            <option value="SOLUSDT">SOLUSDT</option>
          </select>
          <select value={filterAction} onChange={(e) => setFilterAction(e.target.value)}>
            <option value="">Todas acciones</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
            <option value="HOLD">HOLD</option>
          </select>
        </div>
        <table className="data">
          <thead>
            <tr>
              <th>Hora</th>
              <th>Mercado</th>
              <th>Acción</th>
              <th>Cantidad</th>
              <th>Precio</th>
              <th>Motivo</th>
              <th>Comisión</th>
              <th>P/L</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {historyRows.map((r) => (
              <tr key={String(r.id)}>
                <td>{fmtTime(r.at as string)}</td>
                <td>{String(r.symbol)}</td>
                <td>{String(r.action)}</td>
                <td>{r.qty == null ? "—" : fmtNum(r.qty as number, 6)}</td>
                <td>{fmtNum(r.price as number, 4)}</td>
                <td>
                  {String(r.reason)}
                  {r.score != null ? ` · score ${fmtNum(r.score as number, 2)}` : ""}
                </td>
                <td>{r.fee == null ? "—" : fmtNum(r.fee as number, 4)}</td>
                <td>{r.pnl == null ? "—" : fmtNum(r.pnl as number, 4)}</td>
                <td>{String(r.state)}</td>
              </tr>
            ))}
            {!historyRows.length && (
              <tr>
                <td colSpan={9} className="muted">
                  Sin movimientos aún
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          SIGNAL_ONLY = decisión registrada sin fill. FILLED = ejecución virtual real en el ledger
          DEMO.
        </p>
      </div>
    </div>
  );
}
