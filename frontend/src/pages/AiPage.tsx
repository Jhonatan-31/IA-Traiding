import { useEffect, useState } from "react";
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

export default function AiPage() {
  const [status, setStatus] = useState<MlStatus | null>(null);
  const [preds, setPreds] = useState<MlPrediction[]>([]);
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [s, p, c] = await Promise.all([
        api.mlStatus(),
        api.mlPredictions(50),
        api.mlComparison(),
      ]);
      setStatus(s);
      setPreds(p);
      setComparison(c);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function runShadow() {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.mlShadowRun(12);
      setMsg(
        `Shadow run: ${r.generated} predicciones registradas. No se ejecutaron órdenes.`
      );
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error shadow");
    } finally {
      setBusy(false);
    }
  }

  const state = status?.state ?? "untrained";
  const auc = status?.latest_model?.mean_roc_auc_hist_gb;
  const naive = status?.latest_model?.mean_roc_auc_naive;

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Inteligencia artificial</h2>
          <p>
            Investigación cuantitativa. Shadow AI registra señales; no opera ni
            siquiera en paper.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void load()}>
            Actualizar
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
          <div className="stat-label">ROC-AUC walk-forward (HGB)</div>
          <div className="stat-value">
            {auc == null ? "Sin datos" : fmtNum(auc, 4)}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">ROC-AUC naive</div>
          <div className="stat-value">
            {naive == null ? "Sin datos" : fmtNum(naive, 4)}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">Predicciones</div>
          <div className="stat-value">{status?.prediction_count ?? "Sin datos"}</div>
        </div>
        <div className="card">
          <div className="stat-label">Pendientes de resolución</div>
          <div className="stat-value">{status?.pending_resolution ?? "Sin datos"}</div>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <div className="card">
          <h3>Modelo</h3>
          {!status?.latest_model ? (
            <p className="muted">Modelo no disponible. Ejecute el job ml-train.</p>
          ) : (
            <>
              <p>Versión: {status.latest_model.version}</p>
              <p>Creado: {fmtTime(status.latest_model.created_at)}</p>
              <p>Status DB: {status.latest_model.status}</p>
              <p>
                Validado investigación:{" "}
                {status.latest_model.validated_for_research ? "sí" : "no"}
              </p>
              <p className="muted" style={{ marginTop: 8, fontSize: 12 }}>
                {status.latest_model.disclaimer ??
                  "Sin métricas inventadas. PAPER_AI no auto-habilitado."}
              </p>
            </>
          )}
        </div>
        <div className="card">
          <h3>Comparativa fuera de muestra</h3>
          {!comparison?.available ? (
            <p className="muted">Sin datos de walk-forward todavía.</p>
          ) : (
            <>
              <p>HGB AUC medio: {fmtNum(comparison.mean_roc_auc_hist_gb as number, 4)}</p>
              <p>Naive AUC medio: {fmtNum(comparison.mean_roc_auc_naive as number, 4)}</p>
              <p className="muted" style={{ fontSize: 12 }}>
                Detalle de folds disponible vía API /api/ml/comparison. Una AUC
                superior a 0.5 no implica rentabilidad.
              </p>
            </>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Historial de predicciones (Shadow)</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Modelo</th>
                <th>Símbolo</th>
                <th>Prob.</th>
                <th>Acción propuesta</th>
                <th>Gate</th>
                <th>Label obs.</th>
              </tr>
            </thead>
            <tbody>
              {preds.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    Sin predicciones. Entrene y ejecute Shadow AI.
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
                    <td>{p.reject_reason ?? (p.accepted ? "shadow_log" : "—")}</td>
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
