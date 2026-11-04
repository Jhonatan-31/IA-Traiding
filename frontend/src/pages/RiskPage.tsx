import { useEffect, useState } from "react";
import { api, type Overview, type RiskReport } from "../api";
import { EmptyState } from "../components/ui/EmptyState";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { money, pct } from "../ui/format";
import { METRIC_HELP } from "../ui/labels";

const CLASS_LABEL: Record<string, string> = {
  cash: "Saldo disponible (confirmado)",
  invested_cost: "Importe invertido (confirmado)",
  equity_estimate: "Valor total (estimado)",
  unrealized_pnl: "Resultado estimado",
  realized_pnl: "Resultado realizado",
  fees_estimated: "Comisiones estimadas",
  drawdown: "Caída desde el máximo",
};

export default function RiskPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [risk, setRisk] = useState<RiskReport | null>(null);
  const [demo, setDemo] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    setError(null);
    let attempt = 0;
    while (attempt < 3) {
      const [oRes, rRes, dRes] = await Promise.allSettled([
        api.overview(),
        api.risk(),
        api.demoStatus(),
      ]);
      if (oRes.status === "fulfilled") setOverview(oRes.value);
      if (rRes.status === "fulfilled") setRisk(rRes.value);
      if (dRes.status === "fulfilled") setDemo(dRes.value);
      if (oRes.status === "fulfilled" || rRes.status === "fulfilled") {
        setLoading(false);
        if (oRes.status === "rejected" || rRes.status === "rejected") {
          setError("Parte de la información de seguridad no está disponible ahora.");
        }
        return;
      }
      attempt += 1;
      await new Promise((r) => setTimeout(r, 400 * 2 ** (attempt - 1)));
    }
    setLoading(false);
    setError("No pudimos cargar la información de seguridad. Inténtalo de nuevo.");
  }

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30000);
    return () => window.clearInterval(id);
  }, []);

  async function toggle() {
    if (!overview) return;
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      if (overview.engine?.paused) {
        await api.resume("dashboard_resume");
        setMsg("Simulación reanudada. El historial se conserva.");
      } else {
        await api.pause("dashboard_pause");
        setMsg("Simulación en pausa voluntaria: no habrá nuevas compras ni ventas del motor principal.");
      }
      await load();
    } catch {
      setError("No se pudo cambiar el estado del motor. Revisa la conexión.");
    } finally {
      setBusy(false);
    }
  }

  const paused = !!overview?.engine?.paused;
  const demoRunning = String(demo?.bot_status || "") === "RUNNING";

  return (
    <div>
      <PageHeader
        title="Seguridad y protección"
        subtitle="Protecciones virtuales, límites y estado del motor. Los stops dependen de que el servicio y el equipo estén en marcha."
        actions={
          <div className="actions">
            <button className="btn" onClick={() => void load()}>
              Actualizar
            </button>
            <button
              className={`btn ${paused ? "btn-primary" : "btn-danger"}`}
              disabled={busy || !overview}
              onClick={() => void toggle()}
            >
              {paused ? "Reanudar simulación" : "Pausar simulación"}
            </button>
          </div>
        }
      />

      {error && <div className="error-box">{error}</div>}
      {msg && <div className="success-box">{msg}</div>}
      {loading && !risk && <p className="loading-block">Cargando protecciones…</p>}

      <div className="bot-status-line" style={{ marginBottom: 14 }}>
        <StatusBadge variant="info">SIMULACIÓN</StatusBadge>
        <StatusBadge variant={paused ? "warn" : "ok"}>
          Motor principal · {paused ? "Pausa voluntaria" : "Activo"}
        </StatusBadge>
        <StatusBadge variant={demoRunning ? "ok" : "warn"}>
          Bot Demo · {demoRunning ? "En marcha" : "Detenido"}
        </StatusBadge>
      </div>

      <div className="metric-grid">
        <MetricCard label="Saldo disponible" value={money(risk?.cash)} hint={METRIC_HELP.cash} />
        <MetricCard label="Importe invertido" value={money(risk?.invested_cost)} />
        <MetricCard
          label="Valor total"
          value={money(risk?.equity_estimate)}
          hint={METRIC_HELP.equity}
          tone="brand"
        />
        <MetricCard
          label="Resultado realizado"
          value={money(risk?.realized_pnl, { signed: true })}
          hint={METRIC_HELP.realized}
        />
        <MetricCard
          label="Resultado estimado"
          value={money(risk?.unrealized_pnl, { signed: true })}
          hint={METRIC_HELP.unrealized}
        />
        <MetricCard label="Comisiones" value={money(risk?.fees_estimated)} hint={METRIC_HELP.fees} />
        <MetricCard
          label="Caída actual"
          value={
            risk?.drawdown.current_drawdown_pct == null
              ? "—"
              : pct(risk.drawdown.current_drawdown_pct)
          }
          tone="warn"
          hint={METRIC_HELP.drawdown}
        />
        <MetricCard
          label="Caída máxima"
          value={
            risk?.drawdown.max_drawdown_pct == null ? "—" : pct(risk.drawdown.max_drawdown_pct)
          }
          tone="warn"
        />
      </div>

      <div className="two-col">
        <div className="panel">
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>Límites de protección</h3>
          <div className="pos-row">
            <span>Exposición máxima</span>
            <strong>{risk?.limits.max_exposure_pct ?? "—"}%</strong>
          </div>
          <div className="pos-row">
            <span>Caída máxima permitida</span>
            <strong>{risk?.limits.max_drawdown_pct ?? "—"}%</strong>
          </div>
          <div className="pos-row">
            <span>Pérdida diaria máxima</span>
            <strong>{risk?.limits.max_daily_loss_pct ?? "—"}%</strong>
          </div>
          <div className="pos-row">
            <span>Posiciones máximas</span>
            <strong>{risk?.limits.max_positions ?? "—"}</strong>
          </div>
          <div className="pos-row">
            <span>Operaciones por día</span>
            <strong>{risk?.limits.max_trades_per_day ?? "—"}</strong>
          </div>
          <div className="pos-row">
            <span>Límite por operación</span>
            <strong>{money(risk?.limits.per_trade_budget ?? 25)}</strong>
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.45 }}>
            En el Bot Demo, la protección de pérdida típica es cerca de −1% y el objetivo cerca de
            +2%. No garantizan el precio exacto de ejecución.
          </p>
          <p style={{ fontSize: 13, marginTop: 8 }}>
            Alertas activas:{" "}
            {risk?.breaches?.length ? risk.breaches.join(", ") : "ninguna"}
          </p>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>Cómo leer los datos</h3>
          {risk &&
            Object.entries(risk.classification).map(([k, v]) => (
              <div className="pos-row" key={k}>
                <span>{CLASS_LABEL[k] || k}</span>
                <strong>{v === "confirmed" ? "Confirmado" : v === "estimated" ? "Estimado" : String(v)}</strong>
              </div>
            ))}
          <p className="muted" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.45 }}>
            Una pausa voluntaria no es lo mismo que una desconexión: en pausa tú detienes el motor;
            si el servicio o el computador se apagan, las protecciones dejan de vigilar el mercado.
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <h3 style={{ marginTop: 0, color: "var(--text)" }}>Exposición por mercado</h3>
        {(risk?.exposure_by_asset ?? []).length === 0 ? (
          <EmptyState
            title="Sin posiciones abiertas"
            description="Cuando haya compras virtuales, verás aquí el importe invertido y el resultado estimado."
          />
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Mercado</th>
                  <th>Importe invertido</th>
                  <th>Valor de mercado</th>
                  <th>Resultado estimado</th>
                  <th>Tipo de dato</th>
                </tr>
              </thead>
              <tbody>
                {risk!.exposure_by_asset.map((e) => (
                  <tr key={e.symbol}>
                    <td>{e.symbol.replace("USDT", "")}</td>
                    <td className="tabular">{money(e.cost)}</td>
                    <td className="tabular">{money(e.market_value)}</td>
                    <td className="tabular">{money(e.unrealized_pnl, { signed: true })}</td>
                    <td>{e.valuation === "mark" ? "Precio de mercado" : String(e.valuation)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
