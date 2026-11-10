import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Overview, type Position, type Scan } from "../api";
import { ActivityFeed, type FeedItem } from "../components/ui/ActivityFeed";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { clock, money, pct, pnlTone, when } from "../ui/format";
import {
  METRIC_HELP,
  accountLabel,
  actionLabel,
  botNarrative,
  reasonLabel,
} from "../ui/labels";

type AccountKey = "demo" | "paper";

export default function OverviewPage() {
  const [account, setAccount] = useState<AccountKey>("demo");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [scans, setScans] = useState<Scan[]>([]);
  const [demo, setDemo] = useState<Record<string, unknown> | null>(null);
  const [fills, setFills] = useState<Array<Record<string, unknown>>>([]);
  const [decisions, setDecisions] = useState<Array<Record<string, unknown>>>([]);
  const [economic, setEconomic] = useState<Record<string, unknown> | null>(null);
  const [improve, setImprove] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setError(null);
      const [o, p, s, d, f, dec, eco, imp] = await Promise.all([
        api.overview(),
        api.positions(),
        api.scans(),
        api.demoStatus().catch(() => null),
        api.demoFills(30).catch(() => []),
        api.demoDecisions(40).catch(() => []),
        api.activeEconomic().catch(() => null),
        api.researchImprove(false).catch(() => null),
      ]);
      setOverview(o);
      setPositions(p);
      setScans(s);
      setDemo(d);
      setFills(f || []);
      setDecisions(dec || []);
      setEconomic(eco);
      setImprove(imp);
    } catch (e) {
      setError(
        e instanceof Error
          ? "No pudimos actualizar el resumen. Comprueba la conexión e inténtalo de nuevo."
          : "Información temporalmente no disponible."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 20000);
    return () => clearInterval(id);
  }, []);

  const demoPositions = ((demo?.positions as Array<Record<string, unknown>>) || []) as Array<
    Record<string, unknown>
  >;
  const bot = String(demo?.bot_status || "");
  const lastDec = decisions[0];
  const narrative = botNarrative({
    status: bot,
    lastReason: lastDec ? String(lastDec.reason || "") : null,
    lastAction: lastDec ? String(lastDec.action || "") : null,
    lastSymbol: lastDec ? String(lastDec.symbol || "").replace("USDT", "") : null,
    openPositions: demoPositions.length,
  });

  const metrics = useMemo(() => {
    if (account === "demo" && demo) {
      const equity = Number(demo.equity);
      const cash = Number(demo.cash);
      const realized = Number(demo.realized_pnl);
      const unrealized = Number(demo.unrealized_pnl);
      const tc = (demo.trade_counts as Record<string, number>) || {};
      const trades = (tc.buys || 0) + (tc.sells || 0);
      return {
        equity: Number.isFinite(equity) ? equity : null,
        cash: Number.isFinite(cash) ? cash : null,
        dayPnl:
          Number.isFinite(realized) && Number.isFinite(unrealized)
            ? realized + unrealized
            : Number.isFinite(realized)
              ? realized
              : null,
        trades,
        open: demoPositions.length,
        label: accountLabel("demo_manual_control"),
      };
    }
    const equity = overview?.equity_estimate ?? null;
    const initial = overview?.initial_capital ?? 1000;
    return {
      equity,
      cash: overview?.cash ?? null,
      dayPnl: equity != null ? equity - initial : null,
      trades: null as number | null,
      open: overview?.positions ?? positions.length,
      label: accountLabel("sma_paper"),
    };
  }, [account, demo, overview, positions, demoPositions.length]);

  const chartData = useMemo(() => {
    if (account === "demo") {
      // Sin serie histórica dedicada DEMO: declarar cobertura limitada.
      return [] as Array<{ t: string; equity: number }>;
    }
    return scans.map((s) => ({
      t: new Date(s.at).toLocaleString("es-CO", {
        timeZone: "America/Bogota",
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
      }),
      equity: s.equity,
    }));
  }, [account, scans]);

  const feed: FeedItem[] = useMemo(() => {
    const items: FeedItem[] = [];
    for (const t of fills.slice(0, 12)) {
      const side = String(t.side || "").toUpperCase();
      const sym = String(t.symbol || "").replace("USDT", "");
      items.push({
        id: `f-${t.id}`,
        time: clock(String(t.at)),
        title: `${sym} — ${side === "BUY" ? "Compra virtual ejecutada" : "Venta virtual ejecutada"}`,
        detail: reasonLabel(String(t.reason || "")),
        tone: side === "BUY" ? "buy" : side === "SELL" ? "sell" : "info",
      });
    }
    for (const d of decisions.slice(0, 12)) {
      if (d.executed) continue;
      const act = String(d.action || "").toUpperCase();
      const sym = String(d.symbol || "").replace("USDT", "");
      items.push({
        id: `d-${d.id}`,
        time: clock(String(d.at)),
        title: `${sym} — ${actionLabel(act)}. ${reasonLabel(String(d.reason || ""))}`,
        tone: act === "HOLD" ? "hold" : act === "BUY" ? "info" : "warn",
      });
    }
    return items
      .sort((a, b) => b.time.localeCompare(a.time))
      .slice(0, 10);
  }, [fills, decisions]);

  if (loading && !overview && !demo) {
    return <p className="loading-block">Preparando el resumen…</p>;
  }

  const dayTone = pnlTone(metrics.dayPnl);

  return (
    <div>
      <PageHeader
        eyebrow="Resumen ejecutivo"
        title="¿Cómo va tu cuenta?"
        subtitle="Vista clara del capital virtual, del Bot Demo y de la actividad reciente. Cada cuenta se muestra por separado."
        actions={
          <>
            <label className="muted" style={{ fontSize: 12 }}>
              Cuenta{" "}
              <select
                className="account-select"
                value={account}
                onChange={(e) => setAccount(e.target.value as AccountKey)}
                aria-label="Seleccionar cuenta"
              >
                <option value="demo">Bot Demo (dinero virtual propio)</option>
                <option value="paper">Cuenta papel (motor principal)</option>
              </select>
            </label>
            <button type="button" className="btn" onClick={() => void load()}>
              Actualizar
            </button>
          </>
        }
      />

      {error && <div className="error-box">{error}</div>}

      <BotHealthSection economic={economic} />
      <ImproveBotSection improve={improve} onRefreshBacktest={async () => {
        try {
          const imp = await api.researchImprove(true);
          setImprove(imp);
        } catch {
          setError("No pudimos calcular las pruebas históricas de mejora.");
        }
      }} />

      <p className="muted" style={{ marginBottom: 12, fontSize: 13 }}>
        Mostrando: <strong style={{ color: "var(--text)" }}>{metrics.label}</strong>. Las cuentas no se
        suman entre sí.
      </p>

      <div className="metric-grid">
        <MetricCard
          label="Valor total"
          value={money(metrics.equity)}
          hint={METRIC_HELP.equity}
          tone="brand"
        />
        <MetricCard label="Saldo disponible" value={money(metrics.cash)} hint={METRIC_HELP.cash} />
        <MetricCard
          label="Resultado (estimado)"
          value={money(metrics.dayPnl, { signed: true })}
          hint="Resultado de esta cuenta respecto al capital de referencia. No es una promesa de rentabilidad."
          tone={dayTone === "pos" ? "pos" : dayTone === "neg" ? "neg" : "default"}
          sub={
            metrics.dayPnl != null && metrics.equity != null && account === "paper"
              ? pct(((metrics.dayPnl || 0) / (overview?.initial_capital || 1000)) * 100)
              : undefined
          }
        />
        <MetricCard
          label="Operaciones"
          value={metrics.trades == null ? "—" : metrics.trades}
          hint="Compras y ventas virtuales ejecutadas en esta cuenta."
        />
        <MetricCard label="Posiciones abiertas" value={metrics.open} />
      </div>

      <div className="bot-hero">
        <div className="narrative-card">
          <div className="bot-status-line">
            <StatusBadge variant={bot === "RUNNING" ? "ok" : "warn"} pulse={bot === "RUNNING"}>
              {bot === "RUNNING" ? "Bot Demo en marcha" : "Bot Demo detenido"}
            </StatusBadge>
            <StatusBadge variant="info">SIMULACIÓN</StatusBadge>
          </div>
          <p className="big">¿Qué está haciendo el bot ahora?</p>
          <p style={{ margin: 0, fontSize: 17, lineHeight: 1.4 }}>{narrative}</p>
          <div className="actions" style={{ marginTop: 8 }}>
            <Link to="/demo" className="btn btn-primary">
              Ir al Bot Demo
            </Link>
            <Link to="/mercado" className="btn">
              Ver mercado
            </Link>
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <h3>Actividad reciente</h3>
            <Link to="/movimientos" className="muted" style={{ fontSize: 12 }}>
              Ver todo
            </Link>
          </div>
          <ActivityFeed
            items={feed}
            emptyTitle="Sin movimientos todavía"
            emptyDescription="Cuando inicies el Bot Demo, aquí aparecerán compras, ventas y decisiones."
          />
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-title">
          <h3>Evolución del patrimonio</h3>
          {account === "demo" ? (
            <StatusBadge variant="warn">Cobertura limitada</StatusBadge>
          ) : null}
        </div>
        {account === "demo" ? (
          <p className="muted" style={{ fontSize: 13, lineHeight: 1.45 }}>
            La cuenta Bot Demo aún no publica un historial continuo de patrimonio en esta vista.
            Consulta el valor actual arriba o abre{" "}
            <Link to="/resultados" style={{ color: "var(--brand)" }}>
              Resultados
            </Link>{" "}
            para el análisis disponible.
          </p>
        ) : chartData.length < 2 ? (
          <p className="muted">
            Aún no hay suficientes puntos para dibujar la curva. El sistema registra un punto por
            ciclo de análisis.
          </p>
        ) : (
          <div className="chart-box">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis dataKey="t" stroke="#9caac0" fontSize={11} />
                <YAxis domain={["auto", "auto"]} stroke="#9caac0" fontSize={11} width={70} />
                <Tooltip
                  contentStyle={{
                    background: "#111827",
                    border: "1px solid #273247",
                    borderRadius: 8,
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="equity"
                  stroke="#4F8CFF"
                  strokeWidth={2}
                  dot={false}
                  name="Valor USDT"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {account === "paper" && overview?.latest?.at ? (
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            Último ciclo: {when(overview.latest.at)}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function ImproveBotSection({
  improve,
  onRefreshBacktest,
}: {
  improve: Record<string, unknown> | null;
  onRefreshBacktest: () => Promise<void>;
}) {
  const dash = (improve?.dashboard || null) as Record<string, unknown> | null;
  const ai = (improve?.ai || null) as Record<string, unknown> | null;
  const bt = (improve?.backtest || null) as Record<string, unknown> | null;
  const [busyBt, setBusyBt] = useState(false);

  if (!dash) {
    return (
      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>¿Cómo podemos mejorar mi bot?</h3>
        </div>
        <p className="muted">Preparando el diagnóstico de mejora…</p>
      </section>
    );
  }

  const causes = (dash.main_causes as Array<Record<string, unknown>>) || [];
  const byCrypto = (dash.by_crypto as Array<Record<string, unknown>>) || [];
  const experiments = (dash.experiments as Array<Record<string, unknown>>) || [];
  const oos = ((bt?.oos_rows as Array<Record<string, unknown>>) || []);
  const costs = (dash.costs || {}) as Record<string, unknown>;

  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-title">
        <div>
          <h3 style={{ margin: 0 }}>¿Cómo podemos mejorar mi bot?</h3>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>
            Investigación Etapa U · A y B permanecen detenidos · sin dinero real
          </p>
        </div>
        <button
          type="button"
          className="btn"
          disabled={busyBt}
          onClick={() => {
            setBusyBt(true);
            void onRefreshBacktest().finally(() => setBusyBt(false));
          }}
        >
          {busyBt ? "Calculando…" : "Actualizar pruebas históricas"}
        </button>
      </div>

      <p style={{ fontSize: 14, lineHeight: 1.5 }}>{String(dash.why_lost || "")}</p>

      <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <h4 style={{ marginBottom: 8 }}>Principales causas</h4>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
            {causes.map((c) => (
              <li key={String(c.motivo)}>
                <strong>{String(c.motivo)}</strong>: {money(c.impacto as number, { signed: true })}
              </li>
            ))}
          </ul>
          <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            Comisiones {money(costs.comisiones as number)} · Deslizamiento{" "}
            {money(costs.deslizamiento as number)}
          </p>
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Resultado por criptomoneda</h4>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
            {byCrypto.map((c) => (
              <li key={String(c.name)}>
                <strong>{String(c.name)}</strong>: {money(c.resultado as number, { signed: true })} ·{" "}
                {Number(c.cerradas || 0)} cerradas
              </li>
            ))}
          </ul>
        </div>
      </div>

      <h4 style={{ marginTop: 16 }}>Estrategias experimentales en estudio</h4>
      <ul style={{ paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
        {experiments.map((e) => (
          <li key={String(e.nombre)} style={{ marginBottom: 8 }}>
            <strong>{String(e.nombre)}</strong> — {String(e.que_busca)}{" "}
            <span className="muted">({String(e.evidencia)})</span>
          </li>
        ))}
      </ul>

      {oos.length > 0 && (
        <>
          <h4>Comparación fuera de muestra (descriptiva)</h4>
          <p className="muted" style={{ fontSize: 12 }}>
            {String((bt?.claim as Record<string, unknown> | null)?.reason || dash.comparison_note || "")}
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Variante</th>
                  <th>Resultado neto</th>
                  <th>Compras</th>
                  <th>Acierto</th>
                  <th>Factor beneficio</th>
                </tr>
              </thead>
              <tbody>
                {oos.map((r) => (
                  <tr key={String(r.id)}>
                    <td>{String(r.name || r.id)}</td>
                    <td>{money(r.net_oos as number, { signed: true })}</td>
                    <td>{Number(r.trades || 0)}</td>
                    <td>
                      {r.win_rate == null ? "—" : pct(Number(r.win_rate) * 100, { signed: false })}
                    </td>
                    <td>{r.profit_factor == null ? "—" : Number(r.profit_factor).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="info-box" style={{ marginTop: 12 }}>
        <strong>IA:</strong> {String(ai?.human || "Sin datos.")} Predicciones resueltas:{" "}
        {Number(ai?.resolved || 0)} · Con calibración: {Number(ai?.with_calibration || 0)}.
        PAPER_AI deshabilitado.
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        No se declara ninguna variante rentable con la evidencia actual. A y B siguen detenidos.
      </p>
    </section>
  );
}

function BotHealthSection({ economic }: { economic: Record<string, unknown> | null }) {
  const a = (economic?.A || null) as Record<string, unknown> | null;
  const dash = (a?.dashboard || null) as Record<string, unknown> | null;
  const ab = (economic?.ab_prospective || null) as Record<string, unknown> | null;
  if (!dash) {
    return (
      <section className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-title">
          <h3 style={{ margin: 0 }}>¿Cómo le está yendo a mi bot?</h3>
        </div>
        <p className="muted">Cargando la auditoría económica del Bot Demo…</p>
      </section>
    );
  }
  const byCrypto = (dash.by_crypto as Array<Record<string, unknown>>) || [];
  const lossReasons = (dash.main_loss_reasons as Array<Record<string, unknown>>) || [];
  const tone = pnlTone(dash.net as number);
  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-title">
        <div>
          <h3 style={{ margin: 0 }}>¿Cómo le está yendo a mi bot?</h3>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>
            Auditoría del Bot Demo (Conservadora). Dinero virtual · sin órdenes reales.
          </p>
        </div>
        <Link to="/estrategias" className="btn">
          Ver estrategias
        </Link>
      </div>

      <div className="metric-grid">
        <MetricCard label="Dinero virtual inicial" value={money(dash.initial as number)} />
        <MetricCard label="Valor actual" value={money(dash.current_value as number)} tone="brand" />
        <MetricCard
          label="Ganancia o pérdida neta"
          value={money(dash.net as number, { signed: true })}
          tone={tone === "pos" ? "pos" : tone === "neg" ? "neg" : "default"}
        />
        <MetricCard label="Compras realizadas" value={Number(dash.buys || 0)} />
        <MetricCard label="Ventas realizadas" value={Number(dash.sells || 0)} />
        <MetricCard
          label="Operaciones ganadoras / perdedoras"
          value={`${Number(dash.wins || 0)} / ${Number(dash.losses || 0)}`}
          hint="Solo operaciones completamente cerradas. Las compras abiertas no cuentan como ganadoras."
        />
        <MetricCard label="Comisiones" value={money(dash.fees as number)} hint={METRIC_HELP.fees} />
      </div>

      <p style={{ fontSize: 14, lineHeight: 1.5, marginTop: 8 }}>
        {String(dash.summary_text || "")}
      </p>

      <div className="metric-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 8 }}>
        <div>
          <h4 style={{ marginBottom: 8 }}>Resultado por criptomoneda</h4>
          {byCrypto.length === 0 ? (
            <p className="muted">Sin operaciones cerradas todavía.</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
              {byCrypto.map((c) => (
                <li key={String(c.name)}>
                  <strong>{String(c.name)}</strong>: {money(c.resultado as number, { signed: true })}{" "}
                  · {Number(c.cerradas || 0)} cerradas ({Number(c.ganadoras || 0)} ganadoras /{" "}
                  {Number(c.perdedoras || 0)} perdedoras)
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Principales motivos de pérdidas</h4>
          {lossReasons.length === 0 ? (
            <p className="muted">No hay pérdidas cerradas registradas.</p>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.5 }}>
              {lossReasons.map((r) => (
                <li key={String(r.motivo)}>
                  {String(r.motivo)}: {money(r.resultado as number, { signed: true })} (
                  {Number(r.operaciones || 0)} operaciones)
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {ab && (
        <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
          Comparación justa con Trading Activo: B sigue{" "}
          <strong style={{ color: "var(--text)" }}>{String(ab.b_status || "STOPPED")}</strong>. No se
          inicia sola. Cuando la actives, se usará un mismo punto de partida prospectivo.
        </p>
      )}
    </section>
  );
}
