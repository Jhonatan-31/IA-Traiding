import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { money, pct } from "../ui/format";

export default function ResearchCenterPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (runBt = false) => {
    try {
      setBusy(true);
      const r = await api.researchCenter(runBt);
      setData(r);
      setError(null);
    } catch {
      setError("No pudimos cargar el centro de investigación.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const forensic = (data?.forensic_summary || null) as Record<string, unknown> | null;
  const cards = (data?.strategy_cards as Array<Record<string, unknown>>) || [];
  const ai = (data?.ai || null) as Record<string, unknown> | null;
  const bt = (data?.backtest || null) as Record<string, unknown> | null;
  const lossByExit = (forensic?.loss_by_exit || {}) as Record<string, number>;

  return (
    <div>
      <PageHeader
        eyebrow="Etapa V"
        title="Centro de Investigación de Estrategias"
        subtitle="Investigación cuantitativa en simulación. A y B permanecen detenidos. Ningún resultado histórico se interpreta como garantía de rentabilidad."
        actions={
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void load(true)}
          >
            {busy ? "Calculando…" : "Ejecutar backtest V"}
          </button>
        }
      />

      {error && <div className="error-box">{error}</div>}

      <section className="panel">
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Auditoría exacta de A (forense)</h3>
          <StatusBadge variant={forensic?.matches_prior_report ? "ok" : "warn"}>
            {forensic?.matches_prior_report ? "Cifras verificadas" : "Revisar discrepancias"}
          </StatusBadge>
        </div>
        <div className="metric-grid">
          <MetricCard label="Efectivo en cuenta" value={money(forensic?.cash as number)} />
          <MetricCard
            label="Efectivo reconstruido"
            value={money(forensic?.reconstructed_cash as number)}
          />
          <MetricCard
            label="Discrepancia"
            value={money(forensic?.discrepancy as number, { signed: true })}
          />
          <MetricCard label="Rondas cerradas" value={Number(forensic?.closed_rounds || 0)} />
          <MetricCard
            label="P/L realizado"
            value={money(forensic?.realized_pnl as number, { signed: true })}
          />
          <MetricCard label="Comisiones" value={money(forensic?.fees as number)} />
          <MetricCard label="Slippage" value={money(forensic?.slip as number)} />
        </div>
        <h4>Pérdidas por motivo de salida</h4>
        <ul style={{ fontSize: 13, lineHeight: 1.5 }}>
          {Object.entries(lossByExit).map(([k, v]) => (
            <li key={k}>
              {k}: {money(v, { signed: true })}
            </li>
          ))}
        </ul>
        <p className="muted" style={{ fontSize: 12 }}>
          El P/L neto del simulador ya incluye el efecto del deslizamiento en el precio. Las
          comisiones se listan para atribución, no para restarlas otra vez.
        </p>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Estrategias investigadas</h3>
        </div>
        <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
          {cards.map((c) => (
            <div key={String(c.id)} className="panel" style={{ margin: 0 }}>
              <div className="panel-title">
                <h4 style={{ margin: 0 }}>{String(c.name)}</h4>
                <StatusBadge
                  variant={
                    String(c.status_label).includes("Candidata")
                      ? "ok"
                      : String(c.status_label).includes("Rechazada")
                        ? "warn"
                        : "neutral"
                  }
                >
                  {String(c.status_label)}
                </StatusBadge>
              </div>
              <p style={{ fontSize: 13, lineHeight: 1.45 }}>{String(c.how_it_works)}</p>
              <p className="muted" style={{ fontSize: 12 }}>
                Mercados: {(c.markets as string[])?.join(", ")}
              </p>
              <div className="metric-grid">
                <MetricCard
                  label="Resultado neto OOS"
                  value={money(c.net_oos as number | null, { signed: true })}
                />
                <MetricCard
                  label="Drawdown OOS"
                  value={
                    c.drawdown_oos == null
                      ? "—"
                      : pct(Number(c.drawdown_oos) * 100, { signed: false })
                  }
                />
                <MetricCard
                  label="Comisiones OOS"
                  value={money((c.costs_oos as Record<string, number> | null)?.fees)}
                />
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Evidencia: {String(c.evidence)}. {(c.limitations as string[])?.[0]}
              </p>
            </div>
          ))}
        </div>
        {!Boolean(bt?.available) && (
          <p className="muted" style={{ marginTop: 12 }}>
            Pulsa «Ejecutar backtest V» para rellenar métricas fuera de muestra (puede tardar).
          </p>
        )}
        {Boolean(bt?.available) ? (
          <div className="info-box" style={{ marginTop: 12 }}>
            {String((bt?.claim as Record<string, unknown> | null)?.reason || "")}
            <br />
            <span className="muted">{String(bt?.data_span_note || "")}</span>
          </div>
        ) : null}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Inteligencia artificial (solo observación)</h3>
        <p style={{ fontSize: 14 }}>{String(ai?.human || "—")}</p>
        <div className="metric-grid">
          <MetricCard label="Predicciones resueltas" value={Number(ai?.resolved || 0)} />
          <MetricCard label="Con calibración" value={Number(ai?.with_calibration || 0)} />
          <MetricCard
            label="Retorno observado medio"
            value={
              ai?.avg_observed_net_return == null
                ? "—"
                : pct(Number(ai.avg_observed_net_return) * 100)
            }
          />
        </div>
        <p className="muted" style={{ fontSize: 12 }}>
          PAPER_AI deshabilitado. Sin ejecución automática.
        </p>
      </section>

      <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
        {String(data?.conclusion || "")}
      </p>
    </div>
  );
}
