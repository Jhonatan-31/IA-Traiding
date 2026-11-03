import { useEffect, useState } from "react";
import {
  api,
  fmtTime,
  type BinanceDiag,
  type Health,
  type SystemInfo,
} from "../api";

type Tone = "ok" | "warn" | "err" | "info";

function statusOf(ok: boolean | null, labelOk: string, labelBad: string, unknown = false) {
  if (unknown) return { tone: "warn" as Tone, text: "DESCONOCIDO" };
  if (ok) return { tone: "ok" as Tone, text: labelOk };
  return { tone: "err" as Tone, text: labelBad };
}

export default function HealthPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [binance, setBinance] = useState<BinanceDiag | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setError(null);
      const [h, s, b] = await Promise.all([
        api.health(),
        api.system(),
        api.binance(),
      ]);
      setHealth(h);
      setSystem(s);
      setBinance(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 20000);
    return () => clearInterval(id);
  }, []);

  async function runDiag() {
    setBusy(true);
    try {
      await load();
    } finally {
      setBusy(false);
    }
  }

  const apiStatus = statusOf(health?.status === "ok", "OK", "ERROR");
  const dbStatus = statusOf(health?.db === "ok", "OK", "ERROR", !health);
  const binanceStatus =
    binance?.status === "ok"
      ? { tone: "ok" as Tone, text: "OK" }
      : binance
        ? { tone: "err" as Tone, text: "ERROR" }
        : { tone: "warn" as Tone, text: "DESCONOCIDO" };
  const engineStatus = system?.engine?.paused
    ? { tone: "warn" as Tone, text: "PAUSADO" }
    : system?.engine
      ? { tone: "ok" as Tone, text: "ACTIVO" }
      : { tone: "warn" as Tone, text: "DESCONOCIDO" };

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>System Health</h2>
          <p>Diagnóstico de solo lectura. No altera datos de trading.</p>
        </div>
        <button className="btn primary" disabled={busy} onClick={() => void runDiag()}>
          {busy ? "Ejecutando…" : "Ejecutar diagnóstico"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}

      <div className="grid stats" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="stat-label">Backend API</div>
          <div style={{ marginTop: 10 }}>
            <span className={`pill ${apiStatus.tone}`}>{apiStatus.text}</span>
          </div>
        </div>
        <div className="card">
          <div className="stat-label">PostgreSQL</div>
          <div style={{ marginTop: 10 }}>
            <span className={`pill ${dbStatus.tone}`}>{dbStatus.text}</span>
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Binance público</div>
          <div style={{ marginTop: 10 }}>
            <span className={`pill ${binanceStatus.tone}`}>{binanceStatus.text}</span>
          </div>
          <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            {binance?.latency_ms != null
              ? `Latencia ${binance.latency_ms} ms`
              : binance?.error ?? "Sin datos"}
          </p>
        </div>
        <div className="card">
          <div className="stat-label">Simulador / motor</div>
          <div style={{ marginTop: 10 }}>
            <span className={`pill ${engineStatus.tone}`}>{engineStatus.text}</span>
          </div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Recolector</h3>
          <p>Último scan: {fmtTime(system?.last_scan?.at)}</p>
          <p>Mercados: {system?.last_scan?.markets ?? "Sin datos"}</p>
          <p>Errores ciclo: {system?.last_scan?.errors ?? "Sin datos"}</p>
          <p>Equity: {system?.last_scan?.equity ?? "Sin datos"}</p>
          <p>Intervalo: {system?.scan_every_seconds ?? "Sin datos"} s</p>
          <p>Límite scan: {system?.scan_limit ?? "Sin datos"}</p>
        </div>
        <div className="card">
          <h3>Inventario datos</h3>
          <p>Posiciones: {system?.counts.positions ?? "Sin datos"}</p>
          <p>Trades: {system?.counts.trades ?? "Sin datos"}</p>
          <p>Precios: {system?.counts.prices ?? "Sin datos"}</p>
          <p>Scans: {system?.counts.scans ?? "Sin datos"}</p>
          <p>Último trade: {fmtTime(system?.last_trade_at)}</p>
          <p>Precios max at: {fmtTime(system?.prices_max_at)}</p>
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            CPU/RAM de contenedores: no expuestos por la API (evitar datos inventados).
            Revisar `docker stats` en el host.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Bitácora reciente</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Actor</th>
                <th>Acción</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {(system?.audit ?? []).length === 0 ? (
                <tr>
                  <td colSpan={4} className="muted">
                    Sin eventos todavía.
                  </td>
                </tr>
              ) : (
                system!.audit.map((a) => (
                  <tr key={a.id}>
                    <td>{fmtTime(a.at)}</td>
                    <td>{a.actor}</td>
                    <td>{a.action}</td>
                    <td>{a.detail ?? "—"}</td>
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
