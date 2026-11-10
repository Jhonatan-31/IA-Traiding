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

  const load = useCallback(
    async (runBt = false, runBtW = false, runDx = false, runEy = false) => {
      try {
        setBusy(true);
        const r = await api.researchCenter(runBt, runBtW, runDx, runEy);
        setData(r);
        setError(null);
      } catch {
        setError("No pudimos cargar el centro de investigación.");
      } finally {
        setBusy(false);
      }
    },
    []
  );

  useEffect(() => {
    void load(false, false, false, false);
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
  const when = (data?.when_to_trade || null) as Record<string, unknown> | null;
  const lossesReg = (when?.losses_by_regime as Array<Record<string, unknown>>) || [];
  const gainsReg = (when?.gains_by_regime_exploratory as Array<Record<string, unknown>>) || [];
  const hyps = (when?.hypotheses as Array<Record<string, unknown>>) || [];
  const regimePresence = (when?.regime_presence || {}) as Record<string, number>;
  const selling = (data?.selling_too_soon || null) as Record<string, unknown> | null;
  const sellRows = (selling?.comparison_rows as Array<Record<string, unknown>>) || [];
  const sellDiag = (selling?.diagnosis_y0 || {}) as Record<string, Record<string, unknown>>;
  const sellCands = (selling?.candidates as Array<Record<string, unknown>>) || [];
  const sellClaim = (selling?.claim || {}) as Record<string, unknown>;

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

  return (
    <div>
      <PageHeader
        eyebrow="Etapa Y"
        title="Centro de Investigación de Estrategias"
        subtitle="¿Vendemos demasiado pronto? Entradas fijas A/V-BREAK; solo salidas Y0–Y4. A y B detenidos. Sin activación."
        actions={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn" disabled={busy} onClick={() => void runSmoke()}>
              Smoke 1 mes
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void load(false, false, true, false)}
            >
              Diagnóstico régimen
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void load(false, false, false, true)}
            >
              {busy ? "Calculando…" : "Analizar salidas"}
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
          <h3 style={{ margin: 0 }}>¿Cuándo tiene sentido operar?</h3>
          <StatusBadge variant={when?.available ? "ok" : "neutral"}>
            {when?.available ? `Evidencia: ${String(when.evidence_level)}` : "Pendiente"}
          </StatusBadge>
        </div>
        <p style={{ fontSize: 13, lineHeight: 1.45 }}>
          Expectativa en USDT por operación (capital simulado 1.000 USDT). Mínimo 30 operaciones por
          segmento. Holdout de la etapa anterior: consumido — no se reutiliza para elegir ganadores.
        </p>
        {!Boolean(when?.available) && (
          <p className="muted">Pulsa «Diagnóstico por régimen» (usa el historial local de 12 meses).</p>
        )}
        {Boolean(when?.available) && (
          <>
            <h4>Presencia de regímenes (barras BTC 1h)</h4>
            <ul style={{ fontSize: 13, columns: 2, gap: 8 }}>
              {Object.entries(regimePresence)
                .sort((a, b) => Number(b[1]) - Number(a[1]))
                .slice(0, 8)
                .map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
            </ul>
            <h4>Pérdidas netas por régimen (N≥30)</h4>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
              {lossesReg.map((r) => (
                <div key={`${r.strategy}-${r.regime}`} className="panel" style={{ margin: 0 }}>
                  <strong>
                    {String(r.strategy)} · {String(r.regime)}
                  </strong>
                  <div className="metric-grid">
                    <MetricCard label="Ops" value={Number(r.n || 0)} />
                    <MetricCard
                      label="Expectativa"
                      value={money(r.expectancy_usdt as number, { signed: true })}
                    />
                    <MetricCard
                      label="P/L neto"
                      value={money(r.net_pnl_usdt as number, { signed: true })}
                    />
                  </div>
                </div>
              ))}
              {lossesReg.length === 0 && <p className="muted">Sin segmentos perdedores con N suficiente.</p>}
            </div>
            <h4>Ganancias exploratorias (no promoción)</h4>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
              {gainsReg.map((r) => (
                <div key={`g-${r.strategy}-${r.regime}`} className="panel" style={{ margin: 0 }}>
                  <strong>
                    {String(r.strategy)} · {String(r.regime)}
                  </strong>
                  <div className="metric-grid">
                    <MetricCard label="Ops" value={Number(r.n || 0)} />
                    <MetricCard
                      label="Expectativa"
                      value={money(r.expectancy_usdt as number, { signed: true })}
                    />
                  </div>
                  <p className="muted" style={{ fontSize: 12 }}>
                    Exploratorio — puede ser casualidad / selección.
                  </p>
                </div>
              ))}
              {gainsReg.length === 0 && (
                <p className="muted">Ningún segmento con expectativa positiva y N≥30.</p>
              )}
            </div>
            <h4>Hipótesis predefinidas</h4>
            <ul style={{ fontSize: 13 }}>
              {hyps.map((h) => (
                <li key={String(h.id)}>
                  <strong>{String(h.id)}</strong> [{String(h.status)}]: {String(h.text)} —{" "}
                  {String(h.detail)}
                </li>
              ))}
            </ul>
            <div className="info-box" style={{ marginTop: 12 }}>
              {String((when?.claim as Record<string, unknown> | null)?.reason || "")}
              <br />
              <span className="muted">{(when?.limitations as string[])?.[0]}</span>
            </div>
          </>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>¿Estamos vendiendo demasiado pronto?</h3>
          <StatusBadge variant={selling?.available ? "ok" : "neutral"}>
            {selling?.available ? "Análisis listo" : "Pendiente"}
          </StatusBadge>
        </div>
        <p style={{ fontSize: 13, lineHeight: 1.45 }}>
          {String(
            selling?.disclaimer ||
              "El máximo favorable observado no es una ganancia que se podía capturar con certeza."
          )}
        </p>
        {!Boolean(selling?.available) && (
          <p className="muted">Pulsa «Analizar salidas» (puede tardar varios minutos).</p>
        )}
        {Boolean(selling?.available) && (
          <>
            <h4>Diagnóstico con salida original (Y0)</h4>
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
              {(["A_BASELINE", "V_BREAK"] as const).map((mode) => {
                const d = sellDiag[mode] || {};
                return (
                  <div key={mode} className="panel" style={{ margin: 0 }}>
                    <strong>{mode === "A_BASELINE" ? "Estrategia A" : "V-BREAK"}</strong>
                    <div className="metric-grid">
                      <MetricCard
                        label="% MFE &gt; costos"
                        value={
                          d.pct_mfe_gt_costs == null
                            ? "—"
                            : pct(Number(d.pct_mfe_gt_costs) * 100, { signed: false })
                        }
                      />
                      <MetricCard
                        label="% devolvió a pérdida"
                        value={
                          d.pct_gave_back_to_loss == null
                            ? "—"
                            : pct(Number(d.pct_gave_back_to_loss) * 100, { signed: false })
                        }
                      />
                      <MetricCard
                        label="Captura media / MFE"
                        value={
                          d.avg_capture_ratio == null
                            ? "—"
                            : pct(Number(d.avg_capture_ratio) * 100, { signed: false })
                        }
                      />
                      <MetricCard
                        label="Duración media"
                        value={
                          d.avg_duration_min == null
                            ? "—"
                            : `${Number(d.avg_duration_min).toFixed(0)} min`
                        }
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <h4>Comparación de reglas de salida (período comparable)</h4>
            <div style={{ overflowX: "auto" }}>
              <table className="table" style={{ fontSize: 13, width: "100%" }}>
                <thead>
                  <tr>
                    <th>Entrada</th>
                    <th>Salida</th>
                    <th>Ops</th>
                    <th>Neto</th>
                    <th>Expectativa</th>
                    <th>MFE medio</th>
                    <th>Captura</th>
                    <th>Drawdown</th>
                  </tr>
                </thead>
                <tbody>
                  {sellRows.map((r) => (
                    <tr key={`${r.entry}-${r.exit}`}>
                      <td>{String(r.entry)}</td>
                      <td>
                        {String(r.exit)} · {String(r.title || "")}
                      </td>
                      <td>{Number(r.n || 0)}</td>
                      <td>{money(r.net_usdt as number, { signed: true })}</td>
                      <td>{money(r.expectancy as number, { signed: true })}</td>
                      <td>
                        {r.avg_mfe == null
                          ? "—"
                          : pct(Number(r.avg_mfe) * 100, { signed: false })}
                      </td>
                      <td>
                        {r.avg_capture_ratio == null
                          ? "—"
                          : pct(Number(r.avg_capture_ratio) * 100, { signed: false })}
                      </td>
                      <td>
                        {r.drawdown == null
                          ? "—"
                          : pct(Number(r.drawdown) * 100, { signed: false })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h4>Candidatas de investigación</h4>
            <ul style={{ fontSize: 13 }}>
              {sellCands.map((c) => (
                <li key={`${c.entry_mode}-${c.exit_policy}`}>
                  {String(c.entry_mode)} / {String(c.exit_policy)}:{" "}
                  <StatusBadge variant={c.passes_research_filters ? "ok" : "warn"}>
                    {String(c.status)}
                  </StatusBadge>{" "}
                  {(c.filter_notes as string[])?.join(", ")}
                </li>
              ))}
              {sellCands.length === 0 && <li className="muted">Sin resultados aún.</li>}
            </ul>
            <div className="info-box" style={{ marginTop: 12 }}>
              Hipótesis de salida: {String(sellClaim.exit_fix_hypothesis || "—")}.{" "}
              {String(sellClaim.reason || "")}
              <br />
              <span className="muted">{(selling?.limitations as string[])?.[0]}</span>
            </div>
          </>
        )}
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
