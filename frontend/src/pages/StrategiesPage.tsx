import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { money, pct, price, qty, when } from "../ui/format";
import { actionLabel, HOLD_CATEGORY_LABEL, reasonLabel } from "../ui/labels";

const TOKEN_KEY = "lab_control_token";

type Strat = Record<string, unknown>;

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strat[]>([]);
  const [diagnose, setDiagnose] = useState<Record<string, unknown> | null>(null);
  const [history, setHistory] = useState<Record<string, unknown> | null>(null);
  const [compare, setCompare] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [confirmStop, setConfirmStop] = useState(false);
  const [histTab, setHistTab] = useState<"A" | "B">("A");

  const load = useCallback(async () => {
    try {
      const [r, d, h, c] = await Promise.all([
        api.activeStrategies(),
        api.activeDiagnose(),
        api.activeHistory(60),
        api.activeCompare(),
      ]);
      setStrategies(r.strategies || []);
      setDiagnose(d);
      setHistory(h);
      setCompare(c);
      setError(null);
    } catch {
      setError("No pudimos cargar las estrategias. Revisa la conexión del servicio.");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 10000);
    return () => clearInterval(id);
  }, [load]);

  function saveToken(v: string) {
    setToken(v);
    if (v) sessionStorage.setItem(TOKEN_KEY, v);
    else sessionStorage.removeItem(TOKEN_KEY);
  }

  async function startB() {
    if (!token.trim()) {
      setError("Introduce el código de acceso para controlar Trading Activo.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.activeBStart(token.trim());
      setMsg(
        r.changed
          ? "Trading Activo iniciado (dinero virtual, cartera aislada)."
          : "Trading Activo ya estaba en marcha."
      );
      await load();
    } catch (e) {
      setError(
        e instanceof Error && e.message.includes("401")
          ? "Código de acceso incorrecto."
          : "No se pudo iniciar Trading Activo."
      );
    } finally {
      setBusy(false);
    }
  }

  async function stopB() {
    if (!token.trim()) {
      setError("Introduce el código de acceso para detener Trading Activo.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.activeBStop(token.trim());
      setMsg(
        r.changed
          ? "Trading Activo detenido. No abrirá compras nuevas; mantiene protecciones."
          : "Trading Activo ya estaba detenido."
      );
      setConfirmStop(false);
      await load();
    } catch {
      setError("No se pudo detener Trading Activo.");
    } finally {
      setBusy(false);
    }
  }

  const a = strategies.find((s) => s.id === "A");
  const b = strategies.find((s) => s.id === "B");
  const c = strategies.find((s) => s.id === "C");
  const diagA = (diagnose?.A || null) as Record<string, unknown> | null;
  const diagB = (diagnose?.B || null) as Record<string, unknown> | null;
  const histSide = (history?.[histTab] || null) as Record<string, unknown> | null;
  const cmpA = (compare?.A || null) as Record<string, unknown> | null;
  const cmpB = (compare?.B || null) as Record<string, unknown> | null;
  const claim = (compare?.claim || null) as Record<string, unknown> | null;
  const integrity = (compare?.integrity || null) as Record<string, unknown> | null;

  return (
    <div>
      <PageHeader
        eyebrow="Etapa T.1"
        title="Estrategias de Trading"
        subtitle="Comparación operativa A/B/C en simulación. Conservadora y Trading Activo tienen carteras e inicio/detención independientes; la IA solo observa."
        actions={
          <button type="button" className="btn" onClick={() => void load()}>
            Actualizar
          </button>
        }
      />

      {error && <div className="error-box">{error}</div>}
      {msg && <div className="success-box">{msg}</div>}

      <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
        <StrategyCard
          title="Conservadora"
          subtitle="Política Demo 4/5 — referencia"
          strat={a}
          footer={
            <Link to="/demo" className="btn btn-primary">
              Ir al Bot Demo
            </Link>
          }
        />
        <StrategyCard
          title="Trading Activo"
          subtitle="Cruce EMA + filtros de costo — cartera nueva"
          strat={b}
          footer={
            <>
              <div className="token-row" style={{ marginBottom: 10 }}>
                <label htmlFor="active-token">Código de acceso</label>
                <input
                  id="active-token"
                  type="password"
                  value={token}
                  onChange={(e) => saveToken(e.target.value)}
                  placeholder="Mismo token de control Lab/Demo"
                />
              </div>
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy || String(b?.status) === "RUNNING" || !b?.execution_authorized}
                  onClick={() => void startB()}
                >
                  INICIAR
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={busy || String(b?.status) === "STOPPED"}
                  onClick={() => setConfirmStop(true)}
                >
                  DETENER
                </button>
              </div>
              <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                Cartera aislada · no modifica el Bot Demo ni otras cuentas.
              </p>
            </>
          }
        />
        <StrategyCard
          title="IA Experimental"
          subtitle="Solo investigación — sin ejecución"
          strat={c}
          footer={
            <div>
              <StatusBadge variant="warn">IA NO VALIDADA</StatusBadge>
              <p className="muted" style={{ fontSize: 13, marginTop: 10, lineHeight: 1.45 }}>
                {String(c?.last_reason_human || "Sin calibración suficiente para operar.")}
              </p>
              <Link to="/analisis-ia" className="link-btn">
                Ver análisis de IA
              </Link>
            </div>
          }
        />
      </div>

      <section className="panel" style={{ marginTop: 20 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Por qué esperan (HOLD)</h3>
        </div>
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          Porcentajes sobre decisiones únicas por ciclo y símbolo. No se cuentan filas
          repetidas del mismo ciclo como muestras independientes.
        </p>
        <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <HoldPanel title="Conservadora (A)" data={diagA} />
          <HoldPanel title="Trading Activo (B)" data={diagB} />
        </div>
      </section>

      <section className="panel" style={{ marginTop: 20 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>Comparación económica A / B</h3>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          {String(compare?.disclaimer || "Solo datos reales del simulador.")}
        </p>
        {claim && (
          <div className="info-box" style={{ marginBottom: 12 }}>
            {String(claim.reason || "Sin declaración de ganadora.")}
          </div>
        )}
        <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <CompareBlock title="Conservadora" side={cmpA} />
          <CompareBlock title="Trading Activo" side={cmpB} />
        </div>
        {integrity && (
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            Integridad de carteras: {String(integrity.cross_contamination_check)} · Demo cash{" "}
            {money(integrity.demo_cash as number)} · Activo cash {money(integrity.active_cash as number)}
          </p>
        )}
      </section>

      <section className="panel" style={{ marginTop: 20 }}>
        <div className="panel-title" style={{ alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>Historial de operaciones</h3>
          <div className="actions">
            <button
              type="button"
              className={`btn ${histTab === "A" ? "btn-primary" : ""}`}
              onClick={() => setHistTab("A")}
            >
              Conservadora
            </button>
            <button
              type="button"
              className={`btn ${histTab === "B" ? "btn-primary" : ""}`}
              onClick={() => setHistTab("B")}
            >
              Trading Activo
            </button>
          </div>
        </div>
        <HistoryBlock data={histSide} />
      </section>

      <ConfirmDialog
        open={confirmStop}
        title="¿Detener Trading Activo?"
        confirmLabel="Sí, detener"
        danger
        busy={busy}
        onCancel={() => setConfirmStop(false)}
        onConfirm={() => void stopB()}
      >
        <p>Al detener:</p>
        <ul>
          <li>No abrirá compras nuevas.</li>
          <li>Cancelará entradas pendientes.</li>
          <li>Mantendrá protecciones de posiciones abiertas.</li>
        </ul>
      </ConfirmDialog>
    </div>
  );
}

function StrategyCard(props: {
  title: string;
  subtitle: string;
  strat?: Strat;
  footer?: React.ReactNode;
}) {
  const s = props.strat;
  const status = String(s?.status || "—");
  const running = status === "RUNNING";
  const last = s?.last_decision as Record<string, unknown> | null | undefined;
  return (
    <div className="panel">
      <div className="panel-title">
        <div>
          <h3 style={{ margin: 0 }}>{props.title}</h3>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>
            {props.subtitle}
          </p>
        </div>
        <StatusBadge variant={running ? "ok" : status.includes("NO VALIDADA") ? "warn" : "neutral"}>
          {status === "RUNNING" ? "En marcha" : status === "STOPPED" ? "Detenido" : status}
        </StatusBadge>
      </div>
      <div className="metric-grid" style={{ marginBottom: 12 }}>
        <MetricCard label="Saldo virtual" value={money(s?.cash as number | null)} />
        <MetricCard label="Patrimonio" value={money(s?.equity as number | null)} tone="brand" />
        <MetricCard label="Compras" value={Number(s?.buys ?? 0)} />
        <MetricCard label="Ventas" value={Number(s?.sells ?? 0)} />
        <MetricCard label="Posiciones" value={Number(s?.open_positions ?? 0)} />
        <MetricCard
          label="Resultado neto"
          value={money(s?.realized_pnl as number | null, { signed: true })}
        />
      </div>
      <p className="muted" style={{ fontSize: 12 }}>
        Riesgo: {String(s?.risk_level || "—")}
      </p>
      <p style={{ fontSize: 13, marginTop: 8 }}>
        Última decisión:{" "}
        {last
          ? `${actionLabel(String(last.action || ""))} · ${String(last.symbol || "").replace("USDT", "")} · ${when(String(last.at || ""))}`
          : "—"}
      </p>
      <p className="muted" style={{ fontSize: 12, lineHeight: 1.4 }}>
        Motivo:{" "}
        {String(
          s?.last_reason_human ||
            reasonLabel(String((last as Record<string, unknown> | null)?.reason || "")) ||
            "—"
        )}
      </p>
      <div style={{ marginTop: 14 }}>{props.footer}</div>
    </div>
  );
}

function HoldPanel({ title, data }: { title: string; data: Record<string, unknown> | null }) {
  if (!data) {
    return (
      <div>
        <h4 style={{ marginTop: 0 }}>{title}</h4>
        <p className="muted">Sin datos todavía.</p>
      </div>
    );
  }
  const cats = (data.categories as Array<Record<string, unknown>>) || [];
  const top = (data.top_reasons as Array<Record<string, unknown>>) || [];
  return (
    <div>
      <h4 style={{ marginTop: 0 }}>{title}</h4>
      <p className="muted" style={{ fontSize: 12 }}>
        HOLD únicos: {Number(data.unique_cycle_symbol || 0)} · Entrada (sin posición):{" "}
        {Number(data.entry_holds_unique || 0)} · Ciclos de entrada:{" "}
        {Number(data.unique_entry_cycles || 0)}
      </p>
      {cats.length === 0 ? (
        <p className="muted">{String(data.note || "Sin HOLD registrados.")}</p>
      ) : (
        <ul style={{ paddingLeft: 18, margin: "8px 0", fontSize: 13, lineHeight: 1.5 }}>
          {cats.map((c) => (
            <li key={String(c.id)}>
              <strong>{String(c.label || HOLD_CATEGORY_LABEL[String(c.id)] || c.id)}</strong>
              {": "}
              {Number(c.count)} ({pct(Number(c.pct_of_unique_holds), { signed: false })})
            </li>
          ))}
        </ul>
      )}
      {top.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
            Detalle de motivos técnicos
          </summary>
          <ul style={{ paddingLeft: 18, fontSize: 12, lineHeight: 1.45 }}>
            {top.slice(0, 8).map((r) => (
              <li key={String(r.reason)}>
                {String(r.human || reasonLabel(String(r.reason)))} — {Number(r.count)} (
                {pct(Number(r.pct_of_unique_holds), { signed: false })})
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function CompareBlock({
  title,
  side,
}: {
  title: string;
  side: Record<string, unknown> | null;
}) {
  if (!side) {
    return (
      <div>
        <h4 style={{ marginTop: 0 }}>{title}</h4>
        <p className="muted">Sin datos.</p>
      </div>
    );
  }
  const obs = (side.observed || {}) as Record<string, unknown>;
  const fresh = (side.data_freshness || {}) as Record<string, unknown>;
  return (
    <div>
      <h4 style={{ marginTop: 0 }}>{title}</h4>
      <div className="metric-grid">
        <MetricCard label="Capital inicial" value={money(side.initial_capital as number)} />
        <MetricCard label="Patrimonio (proxy)" value={money(side.equity_proxy as number)} />
        <MetricCard
          label="Resultado neto"
          value={money(side.net_result_proxy as number, { signed: true })}
        />
        <MetricCard label="P/L realizado" value={money(side.realized_pnl as number, { signed: true })} />
        <MetricCard label="Compras" value={Number(side.buys || 0)} />
        <MetricCard label="Ventas" value={Number(side.sells || 0)} />
        <MetricCard label="Cerradas" value={Number(side.closed_operations || 0)} />
        <MetricCard label="Comisiones" value={money(side.fees as number)} />
        <MetricCard label="Exposición" value={money(side.exposure_cost as number)} />
        <MetricCard
          label="Drawdown"
          value={
            side.drawdown_proxy == null
              ? "—"
              : pct(Number(side.drawdown_proxy) * 100, { signed: false })
          }
        />
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Estado: {String(obs.status || "—")} · Ciclos: {String(obs.cycle_count ?? "—")} · Datos:{" "}
        {String(fresh.quality || "—")}
        {fresh.last_decision_at ? ` · Última decisión ${when(String(fresh.last_decision_at))}` : ""}
      </p>
      <p className="muted" style={{ fontSize: 11 }}>
        {String(side.equity_note || "")}
      </p>
    </div>
  );
}

function HistoryBlock({ data }: { data: Record<string, unknown> | null }) {
  if (!data) {
    return <p className="muted">Sin historial.</p>;
  }
  const summary = (data.summary || {}) as Record<string, unknown>;
  const trades = (data.trades as Array<Record<string, unknown>>) || [];
  const positions = (data.positions as Array<Record<string, unknown>>) || [];
  const rejects = (data.rejects as Array<Record<string, unknown>>) || [];

  return (
    <div>
      <div className="metric-grid" style={{ marginBottom: 12 }}>
        <MetricCard label="Compras" value={Number(summary.buys || 0)} />
        <MetricCard label="Ventas" value={Number(summary.sells || 0)} />
        <MetricCard label="Abiertas" value={Number(summary.open_positions || 0)} />
        <MetricCard label="Comisiones" value={money(summary.fees as number)} />
        <MetricCard
          label="P/L realizado"
          value={money(summary.realized_pnl as number, { signed: true })}
        />
        <MetricCard label="Rechazos (vista)" value={rejects.length} />
      </div>

      {positions.length > 0 && (
        <>
          <h4>Posiciones abiertas</h4>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Mercado</th>
                  <th>Cantidad</th>
                  <th>Entrada</th>
                  <th>Costo</th>
                  <th>Desde</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={String(p.symbol)}>
                    <td>{String(p.symbol || "").replace("USDT", "")}</td>
                    <td>{qty(p.qty as number)}</td>
                    <td>{price(p.entry_price as number)}</td>
                    <td>{money(p.cost as number)}</td>
                    <td>{when(String(p.opened_at || ""))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h4>Operaciones ejecutadas</h4>
      {trades.length === 0 ? (
        <p className="muted">Sin operaciones en esta cartera (dato real, no inventado).</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Acción</th>
                <th>Mercado</th>
                <th>Precio</th>
                <th>Cantidad</th>
                <th>Comisión</th>
                <th>P/L</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={String(t.id)}>
                  <td>{when(String(t.at || ""))}</td>
                  <td>{actionLabel(String(t.side || ""))}</td>
                  <td>{String(t.symbol || "").replace("USDT", "")}</td>
                  <td>{price(t.price as number)}</td>
                  <td>{qty(t.qty as number)}</td>
                  <td>{money(t.fee as number)}</td>
                  <td>{money(t.realized_pnl as number | null, { signed: true })}</td>
                  <td>{String(t.human_reason || reasonLabel(String(t.reason || "")))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rejects.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary className="muted" style={{ cursor: "pointer" }}>
            Rechazos recientes ({rejects.length})
          </summary>
          <ul style={{ fontSize: 12, lineHeight: 1.45 }}>
            {rejects.slice(0, 20).map((r) => (
              <li key={String(r.id)}>
                {when(String(r.at || ""))} · {String(r.symbol || "—")} ·{" "}
                {reasonLabel(String(r.reason || ""))}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
