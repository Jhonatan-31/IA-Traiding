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
    async (
      runBt = false,
      runBtW = false,
      runDx = false,
      runEy = false,
      runEz = false,
      runEaa = false,
      runEab = false,
      runEac = false
    ) => {
      try {
        setBusy(true);
        const r = await api.researchCenter(runBt, runBtW, runDx, runEy, runEz, runEaa, runEab, runEac);
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
    void load(false, false, false, false, false, false, false, false);
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
  const lab = (data?.advanced_lab || null) as Record<string, unknown> | null;
  const labRows = (lab?.comparison_rows as Array<Record<string, unknown>>) || [];
  const labExec = (lab?.executive || {}) as Record<string, unknown>;
  const labHyps = (lab?.hypotheses_human as Array<Record<string, unknown>>) || [];
  const iv = (data?.independent_validation || null) as Record<string, unknown> | null;
  const ivSparkD = ((iv?.equity_spark as Record<string, unknown> | null)?.d28h5 as Array<Record<string, unknown>>) || [];
  const ivSparkB = ((iv?.equity_spark as Record<string, unknown> | null)?.bh_eq as Array<Record<string, unknown>>) || [];
  const ivLabels = (iv?.labels || {}) as Record<string, string>;
  const vr = (data?.value_vs_risk || null) as Record<string, unknown> | null;
  const po = (data?.prospect_observation || null) as Record<string, unknown> | null;
  const vrLabels = (vr?.labels || {}) as Record<string, string>;
  const sa = (data?.system_audit || null) as Record<string, unknown> | null;
  const adv = (data?.d28h5_advantage || null) as Record<string, unknown> | null;
  const advLabels = (adv?.labels || {}) as Record<string, string>;
  const saVerdicts = (sa?.verdicts || {}) as Record<string, string>;

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
        eyebrow="Etapa AC"
        title="Centro de Investigación de Estrategias"
        subtitle="Auditoría institucional del sistema. A y B detenidos. Sin activación."
        actions={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn" disabled={busy} onClick={() => void runSmoke()}>
              Smoke 1 mes
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void load(false, false, false, false, false, false, true, false)}
            >
              Atribución AB
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void load(false, false, false, false, false, false, false, true)}
            >
              {busy ? "Auditando…" : "Auditoría profesional AC"}
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
          <h3 style={{ margin: 0 }}>Auditoría profesional del sistema</h3>
          <StatusBadge variant={Boolean(sa?.available) ? "warn" : "neutral"}>
            {Boolean(sa?.f01_critical_now) ? "CRÍTICO" : Boolean(sa?.available) ? "Auditado" : "Pendiente"}
          </StatusBadge>
        </div>
        {!Boolean(sa?.available) && (
          <p className="muted">Pulsa «Auditoría profesional AC».</p>
        )}
        {Boolean(sa?.available) && (
          <>
            <div className="metric-grid">
              {Object.entries(saVerdicts).slice(0, 8).map(([k, v]) => (
                <MetricCard key={k} label={k} value={String(v)} />
              ))}
            </div>
            <p style={{ fontSize: 13 }}>
              Runners caídos:{" "}
              {((sa?.runners_down as string[]) || []).length
                ? ((sa?.runners_down as string[]) || []).join(", ")
                : "ninguno detectado"}
              {" · "}Hallazgos: {Number(sa?.findings_n || 0)} · Prospect:{" "}
              {String(sa?.prospect_status || "—")}
            </p>
            <ul style={{ fontSize: 12 }}>
              {((sa?.top_findings as Array<Record<string, unknown>>) || []).map((f) => (
                <li key={String(f.id)}>
                  [{String(f.priority)}] {String(f.id)} — {String(f.title)}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>¿De dónde viene la ventaja de D28H5?</h3>
          <StatusBadge variant="warn">{String(adv?.verdict || "—")}</StatusBadge>
        </div>
        <p className="muted" style={{ fontSize: 12 }}>
          {advLabels.holdout || "Holdout AA consumido"} · no es ganancia absoluta
        </p>
        {Boolean(adv?.available) && (
          <>
            <div className="metric-grid">
              <MetricCard label="D28H5" value={String(adv?.d28h5_net ?? "—")} />
              <MetricCard label="FIXED-55" value={String(adv?.fixed55_net ?? "—")} />
              <MetricCard label="BH-EQ" value={String(adv?.bh_eq_net ?? "—")} />
              <MetricCard label="Efectivo" value={String(adv?.cash_net ?? "—")} />
              <MetricCard label="Δ FIXED-55" value={String(adv?.diff_vs_fixed55 ?? "—")} />
              <MetricCard label="Mercado" value={String(adv?.market_component ?? "—")} />
              <MetricCard label="Exposición" value={String(adv?.exposure_component ?? "—")} />
              <MetricCard label="Activo" value={String(adv?.active_component ?? "—")} />
              <MetricCard label="Costos" value={String(adv?.costs_total ?? "—")} />
            </div>
            <ul style={{ fontSize: 12 }}>
              {((adv?.limitations as string[]) || []).map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
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
          <h3 style={{ margin: 0 }}>Laboratorio de Estrategias Avanzadas</h3>
          <StatusBadge variant={lab?.available ? "ok" : "neutral"}>
            {lab?.available ? "Resultados Z" : "Pendiente"}
          </StatusBadge>
        </div>
        <p style={{ fontSize: 13, lineHeight: 1.45 }}>
          {String(lab?.verdict || "Ejecuta el laboratorio Z para evaluar hipótesis de horizonte mayor.")}
        </p>
        {!Boolean(lab?.available) && (
          <p className="muted">Pulsa «Ejecutar laboratorio Z» (agrega 1d/4h desde Parquet 1m).</p>
        )}
        {Boolean(lab?.available) && (
          <>
            <div className="metric-grid">
              <MetricCard label="Hipótesis" value={Number(labExec.investigated || 0)} />
              <MetricCard label="Descartadas" value={Number(labExec.discarded || 0)} />
              <MetricCard label="Exploratorias" value={Number(labExec.exploratory || 0)} />
              <MetricCard label="Candidatas" value={Number(labExec.candidates || 0)} />
            </div>
            <h4>Comparador (OOS comparable)</h4>
            <div style={{ overflowX: "auto" }}>
              <table className="table" style={{ fontSize: 13, width: "100%" }}>
                <thead>
                  <tr>
                    <th>Hipótesis</th>
                    <th>TF</th>
                    <th>Neto</th>
                    <th>Drawdown</th>
                    <th>Exposición</th>
                    <th>Costos</th>
                    <th>Stress</th>
                  </tr>
                </thead>
                <tbody>
                  {labRows.map((r) => (
                    <tr key={String(r.id)}>
                      <td>
                        {String(r.id)} · {String(r.title || "")}
                      </td>
                      <td>{String(r.tf || "—")}</td>
                      <td>{money(r.net as number, { signed: true })}</td>
                      <td>
                        {r.drawdown == null
                          ? "—"
                          : pct(Number(r.drawdown) * 100, { signed: false })}
                      </td>
                      <td>
                        {r.exposure == null
                          ? "—"
                          : pct(Number(r.exposure) * 100, { signed: false })}
                      </td>
                      <td>{money(r.costs as number)}</td>
                      <td>{money(r.stress as number, { signed: true })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h4>Qué intenta cada línea</h4>
            <ul style={{ fontSize: 13 }}>
              {labHyps.map((h) => (
                <li key={String(h.id)}>
                  <strong>{String(h.id)}</strong> [{String(h.kind)}]: {String(h.what || h.title)}
                </li>
              ))}
            </ul>
            <div className="info-box" style={{ marginTop: 12 }}>
              {String(lab?.adversarial_summary || "")}
              <br />
              <span className="muted">{(lab?.limitations as string[])?.[0]}</span>
            </div>
          </>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Validación independiente</h3>
          <StatusBadge
            variant={
              String(iv?.verdict || "").includes("CANDIDATA")
                ? "ok"
                : String(iv?.verdict || "") === "RECHAZADA"
                  ? "warn"
                  : Boolean(iv?.available)
                    ? "warn"
                    : "neutral"
            }
          >
            {String(iv?.verdict || (iv?.available ? "Lista" : "Pendiente"))}
          </StatusBadge>
        </div>
        <p style={{ fontSize: 13, lineHeight: 1.45 }}>
          Evaluación temporal de una sola pasada de Z-TSMOM-D28H5 congelada. No es prueba PAPER
          prospectiva ni autorización de activación.
        </p>
        <ul style={{ fontSize: 12, color: "var(--muted, #666)" }}>
          <li>{ivLabels.exploratory_z || "Investigación histórica exploratoria (Etapa Z)"}</li>
          <li>{ivLabels.temporal_aa || "Validación temporal (Etapa AA)"}</li>
          <li>{ivLabels.paper_trial || "Prueba prospectiva PAPER — no autorizada aquí"}</li>
        </ul>
        {!Boolean(iv?.available) && (
          <p className="muted">Pulsa «Validación independiente AA» (ingesta 1d + motor + veredicto).</p>
        )}
        {Boolean(iv?.available) && (
          <>
            <div className="metric-grid">
              <MetricCard label="Hash" value={String(iv?.version_hash || "—")} />
              <MetricCard label="Independencia" value={String(iv?.independence || "—")} />
              <MetricCard
                label="D28H5 neto"
                value={money(iv?.d28h5_net as number, { signed: true })}
              />
              <MetricCard
                label="BH-EQ neto"
                value={money(iv?.bh_eq_net as number, { signed: true })}
              />
              <MetricCard
                label="Exceso neto"
                value={money(iv?.excess_net as number, { signed: true })}
              />
              <MetricCard
                label="DD D28H5"
                value={
                  iv?.d28h5_dd == null ? "—" : pct(Number(iv.d28h5_dd) * 100, { signed: false })
                }
              />
              <MetricCard
                label="DD BH-EQ"
                value={iv?.bh_eq_dd == null ? "—" : pct(Number(iv.bh_eq_dd) * 100, { signed: false })}
              />
              <MetricCard
                label="Exposición D28H5"
                value={
                  iv?.d28h5_exposure == null
                    ? "—"
                    : pct(Number(iv.d28h5_exposure) * 100, { signed: false })
                }
              />
            </div>
            <p style={{ fontSize: 13 }}>
              Período: {String((iv?.period as Record<string, unknown> | null)?.start_iso || "—")} →{" "}
              {String((iv?.period as Record<string, unknown> | null)?.end_iso || "—")} · Consumida:{" "}
              {iv?.consumed ? "sí" : "no"}
            </p>
            <p style={{ fontSize: 13 }}>{String(iv?.reason || "")}</p>
            {(ivSparkD.length > 1 || ivSparkB.length > 1) && (
              <div style={{ marginTop: 12 }}>
                <h4 style={{ marginBottom: 8 }}>Patrimonio (spark)</h4>
                <svg viewBox="0 0 600 120" width="100%" height="120" role="img" aria-label="Equity">
                  {(() => {
                    const all = [...ivSparkD, ...ivSparkB].map((p) => Number(p.equity));
                    const mn = Math.min(...all);
                    const mx = Math.max(...all);
                    const span = mx - mn || 1;
                    const path = (pts: Array<Record<string, unknown>>, color: string) => {
                      if (pts.length < 2) return null;
                      const d = pts
                        .map((p, i) => {
                          const x = (i / (pts.length - 1)) * 580 + 10;
                          const y = 110 - ((Number(p.equity) - mn) / span) * 100;
                          return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
                        })
                        .join(" ");
                      return <path d={d} fill="none" stroke={color} strokeWidth="2" />;
                    };
                    return (
                      <>
                        {path(ivSparkD, "#0b6e4f")}
                        {path(ivSparkB, "#5c6b7a")}
                      </>
                    );
                  })()}
                </svg>
                <p className="muted" style={{ fontSize: 12 }}>
                  Verde: D28H5 · Gris: buy&amp;hold equiponderado
                </p>
              </div>
            )}
            <div className="info-box" style={{ marginTop: 12 }}>
              {String(iv?.adversarial_summary || "")}
              <br />
              <span className="muted">{(iv?.limitations as string[])?.[0]}</span>
            </div>
          </>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>¿La estrategia aporta valor o simplemente reduce el riesgo?</h3>
          <StatusBadge variant={Boolean(vr?.available) ? "warn" : "neutral"}>
            {String(vr?.verdict || (vr?.available ? "Lista" : "Pendiente"))}
          </StatusBadge>
        </div>
        <p style={{ fontSize: 12 }} className="muted">
          {vrLabels.simulation || "Simulaciones / atribución AB"} · no es trading
        </p>
        {!Boolean(vr?.available) && (
          <p className="muted">Pulsa «Atribución económica AB».</p>
        )}
        {Boolean(vr?.available) && (
          <>
            <div className="metric-grid">
              <MetricCard label="D28H5" value={money(vr?.d28h5_net as number, { signed: true })} />
              <MetricCard label="BH-EQ" value={money(vr?.bh_eq_net as number, { signed: true })} />
              <MetricCard
                label="Exp. comparable"
                value={money(vr?.exp_match_net as number, { signed: true })}
              />
              <MetricCard label="Efectivo" value={money(vr?.cash_net as number, { signed: true })} />
              <MetricCard
                label="Fixed-55"
                value={money(vr?.fixed55_net as number, { signed: true })}
              />
              <MetricCard
                label="Selección"
                value={money(vr?.selection_contribution as number, { signed: true })}
              />
              <MetricCard
                label="Exposición"
                value={money(vr?.exposure_contribution as number, { signed: true })}
              />
              <MetricCard label="Costos" value={money(vr?.costs as number)} />
              <MetricCard label="Cash days" value={Number(vr?.cash_days || 0)} />
              <MetricCard label="Turnover" value={Number(vr?.turnover || 0)} />
            </div>
            <ul style={{ fontSize: 12 }}>
              {((vr?.warnings as string[]) || []).map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Observación de señales futuras</h3>
          <StatusBadge variant="neutral">{String(po?.status || "—")}</StatusBadge>
        </div>
        <p style={{ fontSize: 13 }}>
          {String(po?.reason_disabled || "Protocolo prospectivo — no es ejecución.")}
        </p>
        <div className="metric-grid">
          <MetricCard label="Protocolo" value={String(po?.protocol_version || "—")} />
          <MetricCard label="Decisiones" value={Number(po?.decisions || 0)} />
          <MetricCard label="Inicio" value={String(po?.start_at || "no iniciado")} />
        </div>
        <p className="muted" style={{ fontSize: 12 }}>
          {(po?.limitations as string[])?.[0] || ""}
        </p>
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
