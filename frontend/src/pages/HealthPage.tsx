import { useEffect, useState } from "react";
import {
  api,
  fmtTime,
  type AlertRow,
  type SystemInfo,
} from "../api";

function pillFor(status?: string) {
  const s = (status || "UNKNOWN").toUpperCase();
  if (s === "OK") return "ok";
  if (s === "WARNING" || s === "WARN") return "warn";
  if (s === "ERROR" || s === "CRITICAL") return "err";
  return "info";
}

export default function HealthPage() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    setError(null);
    let attempt = 0;
    while (attempt < 3) {
      try {
        const [s, a] = await Promise.all([api.system(), api.alerts()]);
        setSystem(s);
        setAlerts(a);
        setLoading(false);
        return;
      } catch (e) {
        attempt += 1;
        if (attempt >= 3) {
          setError(e instanceof Error ? e.message : "Error");
          setLoading(false);
        } else {
          await new Promise((r) => setTimeout(r, 400 * 2 ** (attempt - 1)));
        }
      }
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => {
      void load();
    }, 20000);
    return () => clearInterval(id);
  }, []);

  async function runDiag() {
    setBusy(true);
    try {
      await api.evaluateAlerts();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const comps = system?.components || {};

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Estado del sistema</h2>
          <p>
            Estados basados en evidencia reciente. Sin acceso al socket Docker.
          </p>
        </div>
        <button className="btn primary" disabled={busy} onClick={() => void runDiag()}>
          {busy ? "Evaluando…" : "Diagnóstico + evaluar alertas"}
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      {loading && !system && <p className="muted">Cargando estado del sistema…</p>}

      <div className="grid stats" style={{ marginBottom: 16 }}>
        {Object.entries(comps).map(([name, c]) => (
          <div className="card" key={name}>
            <div className="stat-label">{name}</div>
            <div style={{ marginTop: 10 }}>
              <span className={`pill ${pillFor(c.status)}`}>{c.status}</span>
            </div>
            {c.latency_ms != null && (
              <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                Latencia {c.latency_ms} ms
              </p>
            )}
          </div>
        ))}
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Worker / recolector</h3>
          <p>Último scan: {fmtTime(system?.last_scan?.at)}</p>
          <p>Mercados: {system?.last_scan?.markets ?? "Sin datos"}</p>
          <p>Errores ciclo: {system?.last_scan?.errors ?? "Sin datos"}</p>
          <p>cycle_ms: {(system?.last_scan as { cycle_ms?: number } | null)?.cycle_ms ?? "Sin datos"}</p>
          <p>
            last_candle_ms:{" "}
            {(system?.last_scan as { last_candle_ms?: number } | null)?.last_candle_ms ??
              "Sin datos"}
          </p>
          <p>Intervalo config: {system?.scan_every_seconds ?? "Sin datos"} s</p>
          <p>Fallos 24h: {system?.failed_requests_24h ?? "Sin datos"}</p>
          <p>OHLCV cache: {JSON.stringify(system?.ohlcv_cache ?? {})}</p>
        </div>
        <div className="card">
          <h3>Inventario</h3>
          <p>Posiciones: {system?.counts.positions ?? "Sin datos"}</p>
          <p>Trades: {system?.counts.trades ?? "Sin datos"}</p>
          <p>Precios: {system?.counts.prices ?? "Sin datos"}</p>
          <p>Scans: {system?.counts.scans ?? "Sin datos"}</p>
          <p>Alertas abiertas: {system?.open_alerts ?? "Sin datos"}</p>
          <p>
            Alertas prospectivas:{" "}
            {(system as { prospect_open_alerts?: number } | null)?.prospect_open_alerts ??
              "Sin datos"}
          </p>
          <p>Precios max at: {fmtTime(system?.prices_max_at)}</p>
          <p>Check at: {fmtTime(system?.checked_at)}</p>
          <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
            CPU/RAM: ejecutar `docker stats` en el host (no expuesto aquí).
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Shadow Scheduler (evidencia de heartbeat, no solo contenedor)</h3>
        {(() => {
          const sc = comps.shadow_scheduler;
          const ev = (sc?.evidence || {}) as Record<string, unknown>;
          return (
            <>
              <p>
                Estado:{" "}
                <span className={`pill ${pillFor(sc?.status)}`}>
                  {sc?.status || "UNKNOWN"}
                </span>
              </p>
              <p>Heartbeat: {fmtTime(ev.heartbeat_at as string)} (edad {String(ev.heartbeat_age_s ?? "—")} s)</p>
              <p>Último ciclo: {fmtTime(ev.last_cycle_at as string)} · ok={String(ev.last_cycle_ok ?? "—")}</p>
              <p>
                Última predicción: {fmtTime(ev.last_prediction_at as string)} · Última
                resolución: {fmtTime(ev.last_outcome_at as string)}
              </p>
              <p>
                Pendientes: {String(ev.pending ?? "—")} · Resueltas:{" "}
                {String(ev.resolved ?? "—")} · Inválidas: {String(ev.invalid ?? "—")}
              </p>
              <p>
                Errores inferencia/conexión/resolve: {String(ev.inference_errors ?? 0)} /{" "}
                {String(ev.connection_errors ?? 0)} / {String(ev.resolve_errors ?? 0)}
              </p>
              <p>Modelo activo: {String(ev.active_model_version ?? "Sin datos")}</p>
              {ev.last_error ? (
                <p className="muted" style={{ fontSize: 12 }}>
                  Último error: {String(ev.last_error)}
                </p>
              ) : null}
            </>
          );
        })()}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Alertas internas</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Severidad</th>
                <th>Código</th>
                <th>Título</th>
                <th>Estado</th>
                <th>Actualizado</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    Sin alertas
                  </td>
                </tr>
              ) : (
                alerts.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <span className={`pill ${pillFor(a.severity)}`}>{a.severity}</span>
                    </td>
                    <td>{a.code}</td>
                    <td>{a.title}</td>
                    <td>{a.status}</td>
                    <td>{fmtTime(a.updated_at)}</td>
                    <td>
                      {a.status === "OPEN" && (
                        <button
                          className="btn"
                          onClick={() =>
                            void api.ackAlert(a.id).then(() => load())
                          }
                        >
                          ACK
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Errores recientes del recolector</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Nivel</th>
                <th>Mensaje</th>
              </tr>
            </thead>
            <tbody>
              {(system?.recent_errors ?? []).length === 0 ? (
                <tr>
                  <td colSpan={3} className="muted">
                    Sin eventos
                  </td>
                </tr>
              ) : (
                system!.recent_errors!.map((e) => (
                  <tr key={e.id}>
                    <td>{fmtTime(e.at)}</td>
                    <td>{e.level}</td>
                    <td>{e.message}</td>
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
