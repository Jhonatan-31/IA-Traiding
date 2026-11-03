import { useCallback, useEffect, useState } from "react";
import { api, fmtNum, fmtTime, type MlPrediction, type MlStatus } from "../api";

const STATE_LABEL: Record<string, string> = {
  untrained: "Sin entrenar",
  trained: "Entrenado",
  validation_insufficient: "Validación insuficiente",
  validated_research: "Validado para investigación",
  shadow_ai_active: "Shadow AI activo",
  model_degraded: "Modelo degradado",
  model_disabled: "Modelo deshabilitado",
};

type StratRow = {
  strategy: string;
  mean_net_return_sum?: number | null;
  mean_trades?: number | null;
  mean_max_drawdown?: number | null;
  mean_profit_factor?: number | null;
  net_return_ci?: { mean?: number; low?: number; high?: number } | null;
  robust_edge?: boolean;
};

export default function AiPage() {
  const [status, setStatus] = useState<MlStatus | null>(null);
  const [preds, setPreds] = useState<MlPrediction[]>([]);
  const [resolved, setResolved] = useState<MlPrediction[]>([]);
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const [predSummary, setPredSummary] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [s, p, r, c, sum] = await Promise.all([
        api.mlStatus(),
        api.mlPredictions(40),
        api.mlPredictions(40, { resolvedOnly: true }),
        api.mlComparison(),
        api.mlPredictionsSummary(),
      ]);
      setStatus(s);
      setPreds(p);
      setResolved(r);
      setComparison(c);
      setPredSummary(sum);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error de conexión");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 20000);
    return () => clearInterval(id);
  }, [load]);

  async function runShadow() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.mlShadowRun(12);
      setMsg(`Shadow live: ${r.generated} predicciones. Sin órdenes.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error shadow");
    } finally {
      setBusy(false);
    }
  }

  async function runResolve() {
    setBusy(true);
    try {
      const r = await api.mlResolve();
      setMsg(
        `Resolución: ${r.resolved} resueltas, ${r.still_pending} pendientes de horizonte.`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error resolve");
    } finally {
      setBusy(false);
    }
  }

  async function runReplay() {
    setBusy(true);
    try {
      const r = await api.mlShadowReplay(6);
      setMsg(
        `Replay histórico: ${r.inserted_delta} insertadas (${r.attempted} candidatas), ya resueltas.`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error replay");
    } finally {
      setBusy(false);
    }
  }

  async function evalBreaker() {
    setBusy(true);
    try {
      const r = (await api.mlCircuitEvaluate()) as {
        blocked_new_entries?: boolean;
        reason?: string;
      };
      setMsg(
        r.blocked_new_entries
          ? `Circuit breaker ACTIVO: ${r.reason}`
          : "Circuit breaker inactivo — nuevas entradas simuladas permitidas (SMA)."
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error breaker");
    } finally {
      setBusy(false);
    }
  }

  const state = status?.state ?? "untrained";
  const auc = status?.latest_model?.mean_roc_auc_hist_gb;
  const naive = status?.latest_model?.mean_roc_auc_naive;
  const ece = status?.latest_model?.mean_ece_calibrated_test;
  const strategies = (comparison?.strategy_comparison as StratRow[] | undefined) ?? [];
  const cal = comparison?.calibration as
    | { folds?: { selected?: string; test_after_selection?: Record<string, number> }[] }
    | undefined;

  if (loading && !status) {
    return <p className="muted">Cargando módulo de IA…</p>;
  }

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Inteligencia artificial</h2>
          <p>
            Investigación cuantitativa. Shadow AI registra señales; no opera ni
            siquiera en paper. PAPER_AI no autorizado.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void load()} disabled={busy}>
            Actualizar
          </button>
          <button className="btn" onClick={() => void runResolve()} disabled={busy}>
            Resolver horizonte
          </button>
          <button className="btn" onClick={() => void runReplay()} disabled={busy}>
            Replay histórico
          </button>
          <button className="btn" onClick={() => void evalBreaker()} disabled={busy}>
            Evaluar breaker
          </button>
          <button
            className="btn primary"
            disabled={busy || state === "untrained"}
            onClick={() => void runShadow()}
          >
            {busy ? "Ejecutando…" : "Correr Shadow AI"}
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
          <div className="stat-label">Estado</div>
          <div className="stat-value" style={{ fontSize: 18 }}>
            {STATE_LABEL[state] ?? state}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Versión activa</div>
          <div className="stat-value" style={{ fontSize: 16 }}>
            {status?.runtime?.active_model_version ?? "Sin datos"}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">ROC-AUC HGB</div>
          <div className="stat-value">{auc == null ? "Sin datos" : fmtNum(auc, 4)}</div>
        </div>
        <div className="card">
          <div className="stat-label">ROC-AUC naive</div>
          <div className="stat-value">
            {naive == null ? "Sin datos" : fmtNum(naive, 4)}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">ECE calibrado (test)</div>
          <div className="stat-value">{ece == null ? "Sin datos" : fmtNum(ece, 4)}</div>
        </div>
        <div className="card">
          <div className="stat-label">Circuit breaker</div>
          <div className="stat-value" style={{ fontSize: 16 }}>
            {status?.circuit_breaker?.active
              ? `ACTIVO (${status.circuit_breaker.reason ?? "—"})`
              : "Inactivo"}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Pendientes</div>
          <div className="stat-value">{status?.pending_resolution ?? "Sin datos"}</div>
        </div>
        <div className="card">
          <div className="stat-label">Resueltas</div>
          <div className="stat-value">
            {status?.resolved_count != null
              ? status.resolved_count
              : typeof predSummary?.resolved === "number"
                ? predSummary.resolved
                : "Sin datos"}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Comparativa de rentabilidad neta (walk-forward)</h3>
        <p className="muted" style={{ fontSize: 12 }}>
          Misma política de costos (fee+slip ~0.4% round-trip).{" "}
          <strong>robust_edge</strong> solo si la media neta &gt; 0 y el IC95 inferior
          &gt; 0. No implica promoción a PAPER_AI.
        </p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Estrategia</th>
                <th>Media net_return</th>
                <th>IC95 low</th>
                <th>IC95 high</th>
                <th>Trades medios</th>
                <th>Max DD medio</th>
                <th>PF medio</th>
                <th>Edge robusto</th>
              </tr>
            </thead>
            <tbody>
              {strategies.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted">
                    Sin comparación todavía. Ejecute ml-train.
                  </td>
                </tr>
              ) : (
                strategies.map((row) => (
                  <tr key={row.strategy}>
                    <td>{row.strategy}</td>
                    <td>{fmtNum(row.mean_net_return_sum ?? null, 4)}</td>
                    <td>{fmtNum(row.net_return_ci?.low ?? null, 4)}</td>
                    <td>{fmtNum(row.net_return_ci?.high ?? null, 4)}</td>
                    <td>{fmtNum(row.mean_trades ?? null, 1)}</td>
                    <td>{fmtNum(row.mean_max_drawdown ?? null, 4)}</td>
                    <td>{fmtNum(row.mean_profit_factor ?? null, 3)}</td>
                    <td>{row.robust_edge ? "sí" : "no"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Calibración</h3>
          {!cal?.folds?.length ? (
            <p className="muted">Sin datos de calibración en el modelo activo.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Fold</th>
                    <th>Método (val)</th>
                    <th>Brier test</th>
                    <th>LogLoss test</th>
                    <th>ECE test</th>
                  </tr>
                </thead>
                <tbody>
                  {cal.folds.map((f, i) => (
                    <tr key={i}>
                      <td>{i}</td>
                      <td>{f.selected ?? "—"}</td>
                      <td>{fmtNum(f.test_after_selection?.brier ?? null, 4)}</td>
                      <td>{fmtNum(f.test_after_selection?.log_loss ?? null, 4)}</td>
                      <td>{fmtNum(f.test_after_selection?.ece ?? null, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Método elegido por Brier en validación; métricas mostradas sobre test del
            fold (no se usó test para elegir el calibrador).
          </p>
        </div>
        <div className="card">
          <h3>Precisión observada (resueltas)</h3>
          <p>Accuracy: {fmtNum(predSummary?.accuracy as number | null, 4)}</p>
          <p>Brier proxy: {fmtNum(predSummary?.brier_proxy as number | null, 4)}</p>
          <p>
            Media net_return:{" "}
            {fmtNum(predSummary?.mean_net_return as number | null, 4)}
          </p>
          <p className="muted" style={{ fontSize: 12 }}>
            Incluye replay histórico resuelto y live cuando el horizonte de 6h
            concluya. Las probabilidades históricas no se sobrescriben.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Predicciones Shadow resueltas</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Símbolo</th>
                <th>Fuente</th>
                <th>Prob.</th>
                <th>Acción</th>
                <th>Label</th>
                <th>Net return</th>
                <th>Calidad</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {resolved.length === 0 ? (
                <tr>
                  <td colSpan={8} className="muted">
                    Sin resueltas. Use Replay histórico o espere el horizonte live.
                  </td>
                </tr>
              ) : (
                resolved.map((p) => (
                  <tr key={p.id}>
                    <td>{p.symbol}</td>
                    <td>{p.source ?? "—"}</td>
                    <td>{fmtNum(p.probability, 4)}</td>
                    <td>{p.proposed_action}</td>
                    <td>{p.observed_label}</td>
                    <td>{fmtNum(p.observed_net_return ?? null, 5)}</td>
                    <td>{p.data_quality ?? "—"}</td>
                    <td>{p.resolution_status ?? "RESOLVED"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Historial reciente (incluye pendientes)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Modelo</th>
                <th>Símbolo</th>
                <th>Prob.</th>
                <th>Acción</th>
                <th>Estado</th>
                <th>Label</th>
              </tr>
            </thead>
            <tbody>
              {preds.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    Sin predicciones.
                  </td>
                </tr>
              ) : (
                preds.map((p) => (
                  <tr key={p.id}>
                    <td>{fmtTime(p.created_at)}</td>
                    <td>{p.model_version}</td>
                    <td>{p.symbol}</td>
                    <td>{fmtNum(p.probability, 4)}</td>
                    <td>{p.proposed_action}</td>
                    <td>{p.resolution_status ?? (p.observed_label == null ? "PENDING" : "RESOLVED")}</td>
                    <td>
                      {p.observed_label == null ? "Pendiente" : p.observed_label}
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
