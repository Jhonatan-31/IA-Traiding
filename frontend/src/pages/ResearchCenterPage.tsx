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
  const [histMsg, setHistMsg] = useState<string | null>(null);

  const load = useCallback(async (runBt = false, runBtW = false) => {
    try {
      setBusy(true);
      const r = await api.researchCenter(runBt, runBtW);
      setData(r);
      setError(null);
    } catch {
      setError("No pudimos cargar el centro de investigación.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(false, false);
  }, [load]);

  const forensic = (data?.forensic_summary || null) as Record<string, unknown> | null;
  const cards = (data?.strategy_cards as Array<Record<string, unknown>>) || [];
  const ai = (data?.ai || null) as Record<string, unknown> | null;
  const bt = (data?.backtest || null) as Record<string, unknown> | null;
  const btw = (data?.backtest_w || null) as Record<string, unknown> | null;
  const history = (data?.history || null) as Record<string, unknown> | null;
  const cov = (history?.coverage_report as Record<string, unknown> | null)?.by_symbol as
    | Record<string, Record<string, unknown>>
    | undefined;
  const disk = (history?.disk || null) as Record<string, number> | null;
  const lossByExit = (forensic?.loss_by_exit || {}) as Record<string, number>;

  const runSmoke = async () => {
    try {
      setBusy(true);
      setHistMsg("Descargando smoke (1 mes BTCUSDT)…");
      const r = await api.researchHistorySmoke();
      setHistMsg(
        `Smoke: ${String((r.result as Record<string, unknown> | undefined)?.ingested ? "OK" : "falló")}`
      );
      await load(false, false);
    } catch {
      setHistMsg("Error en descarga smoke.");
    } finally {
      setBusy(false);
    }
  };

  const runExpand = async () => {
    try {
      setBusy(true);
      setHistMsg("Ampliando historial 12 meses (puede tardar varios minutos)…");
      const r = await api.researchHistoryExpand();
      setHistMsg(`Expand: ${Number(r.ingested_ok || 0)}/${Number(r.n_jobs || 0)} meses ingeridos`);
      await load(false, false);
    } catch {
      setHistMsg("Error ampliando historial.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Etapa W"
        title="Centro de Investigación de Estrategias"
        subtitle="Historial Binance Vision + evaluación cuantitativa. A y B detenidos. Más historial no implica rentabilidad."
        actions={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn" disabled={busy} onClick={() => void runSmoke()}>
              Smoke 1 mes
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void runExpand()}>
              Ampliar 12 meses
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void load(false, true)}
            >
              {busy ? "Calculando…" : "Backtest historial W"}
            </button>
          </div>
        }
      />

      {error && <div className="error-box">{error}</div>}
      {histMsg && (
        <p className="muted" style={{ fontSize: 13 }}>
          {histMsg}
        </p>
      )}

      <section className="panel">
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Historial de mercado</h3>
          <StatusBadge variant={String(data?.evidence_level || "").includes("media") ? "ok" : "neutral"}>
            Evidencia: {String(data?.evidence_level || "—")}
          </StatusBadge>
        </div>
        <p style={{ fontSize: 13 }}>
          Fuente: data.binance.vision (Spot). Disponible ≠ verificado. Huecos registrados sin fabricar
          velas.
        </p>
        <div className="metric-grid">
          <MetricCard
            label="Almacenamiento historial"
            value={
              disk?.history_bytes == null
                ? "—"
                : `${(Number(disk.history_bytes) / (1024 * 1024)).toFixed(1)} MB`
            }
          />
          <MetricCard
            label="Disco libre"
            value={
              disk?.disk_free_bytes == null
                ? "—"
                : `${(Number(disk.disk_free_bytes) / (1024 ** 3)).toFixed(1)} GB`
            }
          />
        </div>
        <div className="metric-grid" style={{ marginTop: 8 }}>
          {(["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const).map((sym) => {
            const s = cov?.[sym];
            return (
              <div key={sym} className="panel" style={{ margin: 0 }}>
                <div className="panel-title">
                  <h4 style={{ margin: 0 }}>{sym}</h4>
                  <StatusBadge variant={s?.verified ? "ok" : s?.available ? "warn" : "neutral"}>
                    {s?.verified ? "Verificado" : s?.available ? "Parcial" : "Sin datos"}
                  </StatusBadge>
                </div>
                <p className="muted" style={{ fontSize: 12 }}>
                  {s?.first_iso ? String(s.first_iso).slice(0, 10) : "—"} →{" "}
                  {s?.last_iso ? String(s.last_iso).slice(0, 10) : "—"}
                </p>
                <div className="metric-grid">
                  <MetricCard label="Velas 1m" value={Number(s?.n_bars || 0)} />
                  <MetricCard
                    label="Cobertura"
                    value={s?.coverage_pct == null ? "—" : `${Number(s.coverage_pct).toFixed(2)}%`}
                  />
                  <MetricCard label="Huecos" value={Number(s?.gap_count || 0)} />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
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
        </div>
        <h4>Pérdidas por motivo de salida</h4>
        <ul style={{ fontSize: 13, lineHeight: 1.5 }}>
          {Object.entries(lossByExit).map(([k, v]) => (
            <li key={k}>
              {k}: {money(v, { signed: true })}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Estrategias investigadas</h3>
        </div>
        <div
          className="metric-grid"
          style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}
        >
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
              <div className="metric-grid">
                <MetricCard
                  label="Neto OOS"
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
                <MetricCard label="Ops OOS" value={Number(c.trades_oos || 0)} />
                <MetricCard
                  label="Holdout neto"
                  value={money(c.net_holdout as number | null, { signed: true })}
                />
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Evidencia: {String(c.evidence)}. {(c.limitations as string[])?.[0]}
              </p>
            </div>
          ))}
        </div>
        {Boolean(btw?.available) ? (
          <div className="info-box" style={{ marginTop: 12 }}>
            {String((btw?.claim as Record<string, unknown> | null)?.reason || "")}
            <br />
            <span className="muted">
              Span: {String((btw?.span as Record<string, unknown> | null)?.first_iso || "")} →{" "}
              {String((btw?.span as Record<string, unknown> | null)?.last_iso || "")}
            </span>
          </div>
        ) : (
          <p className="muted" style={{ marginTop: 12 }}>
            Ingesta historial y luego «Backtest historial W». El backtest V corto sigue disponible
            vía API.
          </p>
        )}
        {Boolean(bt?.available) && !Boolean(btw?.available) ? (
          <div className="info-box" style={{ marginTop: 12 }}>
            {String((bt?.claim as Record<string, unknown> | null)?.reason || "")}
          </div>
        ) : null}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Inteligencia artificial (solo observación)</h3>
        <p style={{ fontSize: 14 }}>{String(ai?.human || "—")}</p>
        <div className="metric-grid">
          <MetricCard label="Predicciones resueltas" value={Number(ai?.resolved || 0)} />
          <MetricCard label="Con calibración" value={Number(ai?.with_calibration || 0)} />
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
