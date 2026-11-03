import { useCallback, useEffect, useState } from "react";
import { api, fmtNum, fmtTime } from "../api";

export default function ProspectPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [decisions, setDecisions] = useState<Record<string, unknown>[]>([]);
  const [bench, setBench] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [symbolFilter, setSymbolFilter] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, d, b] = await Promise.all([
        api.prospectStatus(),
        api.prospectDecisions(80, {
          experiment_type: typeFilter || undefined,
          status: statusFilter || undefined,
          symbol: symbolFilter || undefined,
        }),
        api.prospectBenchmarks(),
      ]);
      setStatus(s);
      setDecisions(d);
      setBench(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }, [typeFilter, statusFilter, symbolFilter]);

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

  const counts = (status?.counts as Record<string, number>) || {};
  const virt = (status?.virtual_ledger as Record<string, unknown>) || {};
  const byType = (status?.counts_by_type as Record<string, Record<string, number>>) || {};

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Seguimiento prospectivo</h2>
          <p>
            Decisiones registradas antes del resultado. Separado de backtests y del
            capital paper SMA. PAPER_AI no autorizado.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void load()} disabled={busy}>
            Actualizar
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
        <h3>Benchmark prospectivo (solo SHADOW_LIVE resuelto)</h3>
        <p>Buys resueltos: {String(bench?.resolved_buy_n ?? "Sin datos")}</p>
        <p>
          Media net BUY: {fmtNum(bench?.mean_buy_net as number | null, 5)} · Cash
          benchmark: 0
        </p>
        <p className="muted" style={{ fontSize: 12 }}>
          {String(bench?.note ?? "")}
        </p>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Filtros</h3>
        <div className="actions" style={{ gap: 8, flexWrap: "wrap" }}>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
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
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    Sin decisiones. Pulse «Registrar SHADOW_LIVE».
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
