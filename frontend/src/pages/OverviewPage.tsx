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
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setError(null);
      const [o, p, s, d, f, dec] = await Promise.all([
        api.overview(),
        api.positions(),
        api.scans(),
        api.demoStatus().catch(() => null),
        api.demoFills(30).catch(() => []),
        api.demoDecisions(40).catch(() => []),
      ]);
      setOverview(o);
      setPositions(p);
      setScans(s);
      setDemo(d);
      setFills(f || []);
      setDecisions(dec || []);
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
