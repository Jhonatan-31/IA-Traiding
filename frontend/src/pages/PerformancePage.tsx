import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { money, pct, when } from "../ui/format";
import { METRIC_HELP, accountLabel, statusLabel } from "../ui/labels";

type ComparePayload = {
  generated_at?: string;
  note?: string;
  ledgers?: {
    sma_paper?: Record<string, unknown>;
    lab_auto?: Record<string, unknown>;
    research_sim?: Record<string, unknown>;
  };
  shadow_live?: Record<string, unknown>;
  integrity?: Record<string, unknown>;
  equity_curves?: {
    sma_scans?: Array<{ t: string; equity: number | null; scan_id: number }>;
    lab_daily?: Array<{
      day: string;
      start_equity: number | null;
      end_equity: number | null;
    }>;
    note?: string;
  };
  operational_coverage?: {
    downtime_gaps?: Array<Record<string, unknown>>;
    host_sleep_confirmed_utc?: Record<string, string>;
    policy?: string;
  };
};

function num(v: unknown): number | null {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export default function PerformancePage() {
  const [data, setData] = useState<ComparePayload | null>(null);
  const [demo, setDemo] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [payload, d] = await Promise.all([
        api.performanceCompare(),
        api.demoStatus().catch(() => null),
      ]);
      setData(payload);
      setDemo(d);
      setError(null);
    } catch {
      setError("No pudimos cargar los resultados. Inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const sma = data?.ledgers?.sma_paper || {};
  const lab = data?.ledgers?.lab_auto || {};
  const research = data?.ledgers?.research_sim || {};
  const shadow = data?.shadow_live || {};
  const dd = (sma.drawdown as Record<string, unknown>) || {};
  const gaps = data?.operational_coverage?.downtime_gaps || [];
  const sleep = data?.operational_coverage?.host_sleep_confirmed_utc || {};
  const smaCurve = (data?.equity_curves?.sma_scans || []).map((p) => ({
    label: when(p.t, { withSeconds: false }),
    sma: p.equity,
  }));
  const labCurve = (data?.equity_curves?.lab_daily || []).flatMap((p) => [
    { label: `${p.day} inicio`, lab: p.start_equity },
    { label: `${p.day} fin`, lab: p.end_equity },
  ]);

  return (
    <div>
      <PageHeader
        title="Resultados"
        subtitle="Rendimiento de cada cuenta por separado. No se mezclan capitales. Las predicciones de IA no cuentan como ganancias."
        actions={
          <button className="btn" onClick={() => void load()} disabled={loading}>
            {loading ? "Cargando…" : "Actualizar"}
          </button>
        }
      />

      {error && <div className="error-box">{error}</div>}
      <p className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
        Actualizado: {when(data?.generated_at)} · Solo datos persistidos de simulación
      </p>

      {demo ? (
        <div className="panel" style={{ marginBottom: 14 }}>
          <div className="panel-title">
            <h3>{accountLabel("demo_manual_control")}</h3>
            <StatusBadge variant={String(demo.bot_status) === "RUNNING" ? "ok" : "warn"}>
              {String(demo.bot_status) === "RUNNING" ? "En marcha" : "Detenido"}
            </StatusBadge>
          </div>
          <div className="metric-grid" style={{ marginBottom: 0 }}>
            <MetricCard label="Valor total" value={money(num(demo.equity))} hint={METRIC_HELP.equity} tone="brand" />
            <MetricCard label="Saldo disponible" value={money(num(demo.cash))} hint={METRIC_HELP.cash} />
            <MetricCard
              label="Resultado realizado"
              value={money(num(demo.realized_pnl), { signed: true })}
              hint={METRIC_HELP.realized}
            />
            <MetricCard
              label="Resultado estimado"
              value={money(num(demo.unrealized_pnl), { signed: true })}
              hint={METRIC_HELP.unrealized}
            />
            <MetricCard
              label="Caída desde el máximo"
              value={pct(num(demo.drawdown_vs_peak) != null ? Number(demo.drawdown_vs_peak) * 100 : null)}
              hint={METRIC_HELP.drawdown}
              tone="warn"
            />
          </div>
        </div>
      ) : null}

      <div className="metric-grid">
        <div className="panel">
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>{accountLabel("sma_paper")}</h3>
          <p className="muted" style={{ fontSize: 12 }}>Cuenta del motor principal (simulación).</p>
          <div className="pos-row"><span>Capital inicial</span><strong>{money(num(sma.initial_capital))}</strong></div>
          <div className="pos-row"><span>Saldo disponible</span><strong>{money(num(sma.cash))}</strong></div>
          <div className="pos-row"><span>Invertido</span><strong>{money(num(sma.invested_cost))}</strong></div>
          <div className="pos-row"><span>Valor total</span><strong>{money(num(sma.equity_estimate))}</strong></div>
          <div className="pos-row"><span>Resultado neto</span><strong>{pct(num(sma.net_return_vs_initial) != null ? Number(sma.net_return_vs_initial) * 100 : null)}</strong></div>
          <div className="pos-row"><span>Realizado</span><strong>{money(num(sma.realized_pnl), { signed: true })}</strong></div>
          <div className="pos-row"><span>Estimado</span><strong>{money(num(sma.unrealized_pnl), { signed: true })}</strong></div>
          <div className="pos-row"><span>Comisiones</span><strong>{money(num(sma.fees_estimated))}</strong></div>
          <div className="pos-row"><span>Caída máxima</span><strong>{pct(num(dd.max_drawdown_pct))}</strong></div>
          <div className="pos-row">
            <span>Operaciones</span>
            <strong>
              {String(sma.trades_total ?? "—")} (compras {String(sma.buys ?? 0)} / ventas {String(sma.sells ?? 0)})
            </strong>
          </div>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>{accountLabel("lab_auto")}</h3>
          <p className="muted" style={{ fontSize: 12 }}>
            Estado: {String(lab.valuation_status ?? "—")}
          </p>
          <div className="pos-row"><span>Capital inicial</span><strong>{money(num(lab.initial_capital))}</strong></div>
          <div className="pos-row"><span>Saldo disponible</span><strong>{money(num(lab.cash))}</strong></div>
          <div className="pos-row"><span>Valor total</span><strong>{money(num(lab.equity_estimate))}</strong></div>
          <div className="pos-row"><span>Resultado neto</span><strong>{pct(num(lab.net_return_vs_initial) != null ? Number(lab.net_return_vs_initial) * 100 : null)}</strong></div>
          <div className="pos-row"><span>Realizado</span><strong>{money(num(lab.realized_pnl), { signed: true })}</strong></div>
          <div className="pos-row"><span>Estimado</span><strong>{money(num(lab.unrealized_pnl), { signed: true })}</strong></div>
          <div className="pos-row"><span>Comisiones</span><strong>{money(num(lab.fees_accumulated))}</strong></div>
          <div className="pos-row"><span>Diferencia de ejecución</span><strong>{money(num(lab.slip_total))}</strong></div>
          <div className="pos-row"><span>Posiciones abiertas</span><strong>{String(lab.open_positions ?? "—")}</strong></div>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>Análisis de IA</h3>
          <p className="muted" style={{ fontSize: 12, lineHeight: 1.45 }}>
            Predicciones en evaluación — no usan dinero ni generan resultado de cuenta.
          </p>
          <div className="pos-row"><span>Saldo investigación</span><strong>{money(num(research.cash))}</strong></div>
          <div className="pos-row"><span>En evaluación</span><strong>{String(shadow.pending ?? "—")}</strong></div>
          <div className="pos-row"><span>Completadas</span><strong>{String(shadow.resolved ?? "—")}</strong></div>
          <div className="pos-row"><span>No evaluables</span><strong>{String(shadow.invalid ?? "—")}</strong></div>
          <div className="pos-row">
            <span>Muestra suficiente</span>
            <strong>
              <StatusBadge variant={shadow.sample_sufficient ? "ok" : "warn"}>
                {shadow.sample_sufficient ? "Sí" : "Aún no"}
              </StatusBadge>
            </strong>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
            No se presenta un score interno como probabilidad de ganar.
            {shadow.strategy_claim_allowed
              ? " Hay base para comparar estrategias con cautela."
              : " Todavía no hay base estadística para afirmar una estrategia ganadora."}
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-title">
          <h3>Evolución del patrimonio</h3>
          {data?.equity_curves?.note ? (
            <StatusBadge variant="warn">Cobertura limitada</StatusBadge>
          ) : null}
        </div>
        {data?.equity_curves?.note ? (
          <p className="muted" style={{ fontSize: 13 }}>{String(data.equity_curves.note)}</p>
        ) : null}
        {smaCurve.length < 2 && labCurve.length < 2 ? (
          <p className="muted">Aún no hay suficientes puntos para dibujar la curva.</p>
        ) : (
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={[...smaCurve, ...labCurve]}>
                <CartesianGrid stroke="#273247" strokeDasharray="3 3" />
                <XAxis dataKey="label" stroke="#9caac0" fontSize={11} />
                <YAxis stroke="#9caac0" fontSize={11} width={70} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #273247",
                    borderRadius: 8,
                  }}
                />
                <Legend />
                <Line type="monotone" dataKey="sma" name="Cuenta papel" stroke="#4F8CFF" dot={false} connectNulls />
                <Line type="monotone" dataKey="lab" name="Bot automático" stroke="#17B890" dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {(gaps.length > 0 || Object.keys(sleep).length > 0) && (
        <div className="panel" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>Cobertura operativa</h3>
          <p className="muted" style={{ fontSize: 13, lineHeight: 1.45 }}>
            Periodos en los que el equipo o el servicio no estuvieron activos. Esos tramos no
            deben interpretarse como resultados de mercado.
          </p>
          {Object.keys(sleep).length > 0 && (
            <p className="muted" style={{ fontSize: 12 }}>
              Sueño del equipo confirmado: {Object.entries(sleep).map(([k, v]) => `${k}=${v}`).join(" · ")}
            </p>
          )}
          {gaps.slice(0, 8).map((g, i) => (
            <p key={i} className="muted" style={{ fontSize: 12 }}>
              {String(g.from || g.start || "—")} → {String(g.to || g.end || "—")} ·{" "}
              {String(g.reason || g.note || "pausa")}
            </p>
          ))}
        </div>
      )}

      {data?.integrity ? (
        <p className="muted" style={{ fontSize: 11, marginTop: 12 }}>
          Integridad de datos: {statusLabel(String(data.integrity.status || "OK"))}
        </p>
      ) : null}
    </div>
  );
}
