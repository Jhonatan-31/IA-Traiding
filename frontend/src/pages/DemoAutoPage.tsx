import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ActivityFeed, type FeedItem } from "../components/ui/ActivityFeed";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { EmptyState } from "../components/ui/EmptyState";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { clock, money, pct, pnlTone, price, qty, when } from "../ui/format";
import {
  METRIC_HELP,
  actionLabel,
  botNarrative,
  reasonLabel,
  statusLabel,
} from "../ui/labels";

const TOKEN_KEY = "lab_control_token";
const ONBOARD_KEY = "demo_onboard_v1_dismissed";

function humanApiError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  if (msg.includes("401") || msg.includes("403")) {
    return "No pudimos autorizar el comando. Revisa el código de acceso e inténtalo de nuevo.";
  }
  if (msg.includes("Failed to fetch") || msg.includes("Network")) {
    return "Sin conexión con el servicio. Comprueba que la aplicación esté en marcha.";
  }
  return "No se pudo completar la acción. Inténtalo de nuevo en unos segundos.";
}

function botUiState(bot: string, st: Record<string, unknown>, positions: number): {
  label: string;
  variant: "ok" | "warn" | "danger" | "info" | "neutral";
} {
  if (bot === "STOPPED") return { label: "Detenido", variant: "warn" };
  if (bot !== "RUNNING") return { label: "Revisando…", variant: "neutral" };
  if (st.connection_ok === false) return { label: "Problema de conexión", variant: "danger" };
  if (positions > 0) return { label: "Operando · protegiendo posiciones", variant: "ok" };
  return { label: "Analizando · esperando oportunidad", variant: "ok" };
}

export default function DemoAutoPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [fills, setFills] = useState<Array<Record<string, unknown>>>([]);
  const [decisions, setDecisions] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<"start" | "stop" | null>(null);
  const [confirmStop, setConfirmStop] = useState(false);
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterAction, setFilterAction] = useState("");
  const [explainId, setExplainId] = useState<string | null>(null);
  const [onboardDismissed, setOnboardDismissed] = useState(
    () => localStorage.getItem(ONBOARD_KEY) === "1"
  );
  const [onboardStep, setOnboardStep] = useState(0);

  const load = useCallback(async () => {
    try {
      const [s, f, d] = await Promise.all([
        api.demoStatus(),
        api.demoFills(80, filterSymbol || undefined),
        api.demoDecisions(80, filterSymbol || undefined, filterAction || undefined),
      ]);
      setStatus(s);
      setFills(f);
      setDecisions(d);
      setError(null);
    } catch {
      setError("No pudimos actualizar el Bot Demo. Revisa la conexión del servicio.");
    }
  }, [filterSymbol, filterAction]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [load]);

  function saveToken(v: string) {
    setToken(v);
    if (v) sessionStorage.setItem(TOKEN_KEY, v);
    else sessionStorage.removeItem(TOKEN_KEY);
  }

  async function doStart() {
    if (!token.trim()) {
      setError("Introduce el código de acceso para iniciar o detener el bot.");
      return;
    }
    setBusy(true);
    setPendingAction("start");
    setError(null);
    try {
      const r = await api.demoStart(token.trim());
      await load();
      const confirmed = String(r.status || "").toUpperCase() === "RUNNING" || r.changed;
      setMsg(
        confirmed
          ? "Bot iniciado. Empezará a analizar el mercado con dinero virtual."
          : "El bot ya estaba en marcha."
      );
    } catch (e) {
      setError(humanApiError(e));
    } finally {
      setBusy(false);
      setPendingAction(null);
    }
  }

  async function doStop() {
    if (!token.trim()) {
      setError("Introduce el código de acceso para iniciar o detener el bot.");
      return;
    }
    setBusy(true);
    setPendingAction("stop");
    setError(null);
    try {
      const r = await api.demoStop(token.trim());
      await load();
      setMsg(
        r.changed || String(r.status || "").toUpperCase() === "STOPPED"
          ? "Bot detenido. No abrirá compras nuevas; las protecciones de posiciones siguen activas."
          : "El bot ya estaba detenido."
      );
      setConfirmStop(false);
    } catch (e) {
      setError(humanApiError(e));
    } finally {
      setBusy(false);
      setPendingAction(null);
    }
  }

  const bot = String(status?.bot_status || "—");
  const st = (status?.state as Record<string, unknown>) || {};
  const positions = (status?.positions as Array<Record<string, unknown>>) || [];
  const dc = (status?.decision_counts as Record<string, number>) || {};
  const tc = (status?.trade_counts as Record<string, number>) || {};
  const ui = botUiState(bot, st, positions.length);
  const lastDec = decisions[0];
  const narrative = botNarrative({
    status: bot,
    lastReason: lastDec ? String(lastDec.reason || "") : String(st.last_reason || ""),
    lastAction: lastDec ? String(lastDec.action || "") : null,
    lastSymbol: lastDec ? String(lastDec.symbol || "").replace("USDT", "") : null,
    openPositions: positions.length,
  });

  const equity = Number(status?.equity);
  const cash = Number(status?.cash);
  const realized = Number(status?.realized_pnl);
  const unrealized = Number(status?.unrealized_pnl);
  const net =
    Number.isFinite(realized) && Number.isFinite(unrealized)
      ? realized + unrealized
      : Number.isFinite(realized)
        ? realized
        : null;

  const feed: FeedItem[] = useMemo(() => {
    const items: FeedItem[] = [];
    for (const t of fills) {
      const side = String(t.side || "").toUpperCase();
      const sym = String(t.symbol || "").replace("USDT", "");
      const id = `f-${t.id}`;
      items.push({
        id,
        time: clock(String(t.at)),
        title: `${sym} — ${side === "BUY" ? "Compra virtual ejecutada" : "Venta virtual ejecutada"}`,
        detail: `${price(t.price as number)} · ${reasonLabel(String(t.reason || ""))}`,
        tone: side === "BUY" ? "buy" : "sell",
        onExplain: () => setExplainId(id),
        meta:
          explainId === id ? (
            <div className="explain-box">
              <strong>Qué ocurrió:</strong> operación virtual {side === "BUY" ? "de compra" : "de venta"}.
              <br />
              <strong>Motivo:</strong> {reasonLabel(String(t.reason || ""))}
              <br />
              <strong>Cantidad:</strong> {qty(t.qty as number)} · <strong>Precio:</strong>{" "}
              {price(t.price as number)}
              {t.realized_pnl != null ? (
                <>
                  <br />
                  <strong>Resultado:</strong> {money(t.realized_pnl as number, { signed: true })}
                </>
              ) : null}
            </div>
          ) : null,
      });
    }
    for (const d of decisions) {
      if (d.executed) continue;
      const act = String(d.action || "").toUpperCase();
      const sym = String(d.symbol || "").replace("USDT", "");
      const id = `d-${d.id}`;
      items.push({
        id,
        time: clock(String(d.at)),
        title: `${sym} — ${actionLabel(act)}`,
        detail: reasonLabel(String(d.reason || "")),
        tone: act === "HOLD" ? "hold" : act === "BUY" ? "info" : act === "SELL" ? "warn" : "info",
        onExplain: () => setExplainId(id),
        meta:
          explainId === id ? (
            <div className="explain-box">
              <strong>Tipo:</strong> decisión registrada (no es una operación ejecutada).
              <br />
              <strong>Acción:</strong> {actionLabel(act)}
              <br />
              <strong>Motivo:</strong> {reasonLabel(String(d.reason || ""))}
              <br />
              <strong>Precio observado:</strong> {price(d.observed_price as number)}
              <br />
              <span className="muted">
                La puntuación interna no es una probabilidad de ganar.
              </span>
            </div>
          ) : null,
      });
    }
    return items
      .sort((a, b) => {
        const ta = fills.find((x) => `f-${x.id}` === a.id)?.at || decisions.find((x) => `d-${x.id}` === a.id)?.at;
        const tb = fills.find((x) => `f-${x.id}` === b.id)?.at || decisions.find((x) => `d-${x.id}` === b.id)?.at;
        return String(tb || "").localeCompare(String(ta || ""));
      })
      .slice(0, 40);
  }, [fills, decisions, explainId]);

  const historyRows = useMemo(() => {
    const rows: Array<Record<string, unknown>> = [];
    for (const t of fills) {
      rows.push({
        kind: "FILL",
        at: t.at,
        symbol: t.symbol,
        action: t.side,
        qty: t.qty,
        price: t.price,
        reason: t.reason,
        fee: t.fee,
        pnl: t.realized_pnl,
        state: "FILLED",
        id: `f-${t.id}`,
      });
    }
    for (const d of decisions) {
      if (d.executed) continue;
      rows.push({
        kind: "SIGNAL",
        at: d.at,
        symbol: d.symbol,
        action: d.action,
        qty: null,
        price: d.observed_price,
        reason: d.reason,
        fee: null,
        pnl: null,
        state: "SIGNAL_ONLY",
        id: `d-${d.id}`,
      });
    }
    return rows.sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 60);
  }, [fills, decisions]);

  const onboardCopy = [
    {
      t: "Qué hace el Bot Demo",
      d: "Analiza BTC, ETH y SOL y puede comprar o vender con dinero virtual. No usa dinero real.",
    },
    {
      t: "Cómo iniciar y detener",
      d: "Usa INICIAR BOT para que busque oportunidades. DETENER bloquea compras nuevas y mantiene las protecciones de posiciones abiertas.",
    },
    {
      t: "Dónde ver el resultado",
      d: "Las compras y ventas aparecen en la actividad y en Movimientos. El riesgo y las protecciones están en Seguridad.",
    },
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Centro de control"
        title="Mi Bot de Trading"
        subtitle="El bot analiza mercados y ejecuta operaciones con dinero virtual."
        actions={
          <StatusBadge variant={ui.variant} pulse={bot === "RUNNING"}>
            {ui.label}
          </StatusBadge>
        }
      />

      {!onboardDismissed && (
        <div className="onboarding" role="region" aria-label="Introducción">
          <div>
            <strong>
              Paso {onboardStep + 1} de 3 — {onboardCopy[onboardStep].t}
            </strong>
            <p>{onboardCopy[onboardStep].d}</p>
            <div className="actions" style={{ marginTop: 10 }}>
              {onboardStep < 2 ? (
                <button type="button" className="btn btn-primary" onClick={() => setOnboardStep((s) => s + 1)}>
                  Siguiente
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => {
                    localStorage.setItem(ONBOARD_KEY, "1");
                    setOnboardDismissed(true);
                  }}
                >
                  Entendido
                </button>
              )}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => {
                  localStorage.setItem(ONBOARD_KEY, "1");
                  setOnboardDismissed(true);
                }}
              >
                Omitir
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <div className="error-box">{error}</div>}
      {msg && <div className="success-box">{msg}</div>}

      <div className="bot-hero">
        <div className="bot-control">
          <div className="bot-status-line">
            <StatusBadge variant={bot === "RUNNING" ? "ok" : "warn"} pulse={bot === "RUNNING"}>
              {bot === "RUNNING" ? "En marcha" : "Detenido"}
            </StatusBadge>
            <StatusBadge variant="info">SIMULACIÓN</StatusBadge>
            <span className="muted" style={{ fontSize: 12 }}>
              Última evaluación: {when(st.last_eval_at as string)}
            </span>
          </div>
          <p className="bot-narrative">{narrative}</p>
          <div className="bot-controls-row">
            <button
              type="button"
              className="btn btn-primary btn-lg"
              disabled={busy || bot === "RUNNING"}
              onClick={() => void doStart()}
              aria-label="Iniciar bot"
            >
              {pendingAction === "start" ? "Iniciando…" : "INICIAR BOT"}
            </button>
            <button
              type="button"
              className="btn btn-danger btn-lg"
              disabled={busy || bot === "STOPPED"}
              onClick={() => setConfirmStop(true)}
              aria-label="Detener bot"
            >
              {pendingAction === "stop" ? "Deteniendo…" : "DETENER BOT"}
            </button>
          </div>
          <div className="token-row">
            <label htmlFor="demo-token">Código de acceso (solo en esta sesión)</label>
            <input
              id="demo-token"
              type="password"
              value={token}
              onChange={(e) => saveToken(e.target.value)}
              autoComplete="off"
              placeholder="Necesario para iniciar o detener"
            />
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 12, lineHeight: 1.45 }}>
            Al detener: se bloquean compras nuevas y entradas pendientes; las posiciones abiertas
            siguen con protección de pérdida y objetivo de ganancia mientras el servicio esté
            activo.
          </p>
        </div>

        <div className="panel">
          <div className="panel-title">
            <h3>Resumen de la cuenta Demo</h3>
            <span className="muted" style={{ fontSize: 11 }} title={METRIC_HELP.paper}>
              Dinero virtual
            </span>
          </div>
          <div className="metric-grid" style={{ marginBottom: 0 }}>
            <MetricCard label="Valor total" value={money(equity)} hint={METRIC_HELP.equity} tone="brand" />
            <MetricCard label="Saldo disponible" value={money(cash)} hint={METRIC_HELP.cash} />
            <MetricCard
              label="Ganancia / pérdida"
              value={money(net, { signed: true })}
              tone={pnlTone(net) === "pos" ? "pos" : pnlTone(net) === "neg" ? "neg" : "default"}
              hint="Suma del resultado realizado y el estimado de posiciones abiertas."
            />
            <MetricCard label="Posiciones abiertas" value={positions.length} />
            <MetricCard label="Compras" value={tc.buys ?? 0} />
            <MetricCard label="Ventas" value={tc.sells ?? 0} />
          </div>
          <p className="muted" style={{ fontSize: 12, marginTop: 12 }}>
            Decisiones: {actionLabel("BUY")} {dc.BUY ?? 0} · {actionLabel("SELL")} {dc.SELL ?? 0} ·{" "}
            {actionLabel("HOLD")} {dc.HOLD ?? 0}
          </p>
        </div>
      </div>

      <div className="two-col" style={{ marginTop: 14 }}>
        <div className="panel">
          <div className="panel-title">
            <h3>Actividad en vivo</h3>
            <StatusBadge variant="neutral">Tiempo real</StatusBadge>
          </div>
          <ActivityFeed
            items={feed}
            emptyTitle="El bot aún no ha registrado actividad"
            emptyDescription={
              bot === "STOPPED"
                ? "El bot está detenido. Pulsa INICIAR BOT para que empiece a analizar."
                : "En cuanto haya un ciclo de análisis, verás aquí las decisiones y operaciones."
            }
          />
        </div>

        <div className="panel">
          <div className="panel-title">
            <h3>Posiciones abiertas</h3>
            <Link to="/posiciones" className="muted" style={{ fontSize: 12 }}>
              Ver todas
            </Link>
          </div>
          {positions.length === 0 ? (
            <EmptyState
              title="Sin posiciones abiertas"
              description="Cuando el bot compre, verás aquí la cantidad, el precio y el resultado estimado."
              icon="◎"
            />
          ) : (
            <div className="position-cards">
              {positions.map((p) => {
                const upnl = Number(p.upnl);
                return (
                  <div className="position-card" key={String(p.symbol)}>
                    <h4>{String(p.symbol).replace("USDT", "")}</h4>
                    <div className="pos-row">
                      <span>Cantidad</span>
                      <strong>{qty(p.qty as number)}</strong>
                    </div>
                    <div className="pos-row">
                      <span>Precio de compra</span>
                      <strong>{price(p.entry_price as number)}</strong>
                    </div>
                    <div className="pos-row">
                      <span>Precio de mercado</span>
                      <strong>{price(p.mark as number)}</strong>
                    </div>
                    <div className="pos-row">
                      <span>Resultado estimado</span>
                      <strong style={{ color: upnl >= 0 ? "var(--buy)" : "var(--sell)" }}>
                        {money(upnl, { signed: true })}
                      </strong>
                    </div>
                    <Link
                      to={`/mercado?symbol=${encodeURIComponent(String(p.symbol))}`}
                      className="link-btn"
                    >
                      Abrir gráfico
                    </Link>
                  </div>
                );
              })}
            </div>
          )}
          <p className="muted" style={{ fontSize: 11, marginTop: 10 }}>
            Caída desde el máximo:{" "}
            {pct(
              status?.drawdown_vs_peak != null
                ? Number(status.drawdown_vs_peak) * 100
                : null
            )}{" "}
            · {METRIC_HELP.drawdown}
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <div className="panel-title">
          <h3>Historial comprensible</h3>
        </div>
        <div className="filter-bar">
          <select
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value)}
            aria-label="Filtrar mercado"
          >
            <option value="">Todos los mercados</option>
            <option value="BTCUSDT">BTC</option>
            <option value="ETHUSDT">ETH</option>
            <option value="SOLUSDT">SOL</option>
          </select>
          <select
            value={filterAction}
            onChange={(e) => setFilterAction(e.target.value)}
            aria-label="Filtrar acción"
          >
            <option value="">Todas las acciones</option>
            <option value="BUY">Comprar</option>
            <option value="SELL">Vender</option>
            <option value="HOLD">Esperar</option>
          </select>
        </div>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha y hora</th>
                <th>Mercado</th>
                <th>Qué ocurrió</th>
                <th>Precio</th>
                <th>Cantidad</th>
                <th>Resultado</th>
                <th>Estado</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {historyRows.map((r) => {
                const act = String(r.action || "").toUpperCase();
                const isFill = r.kind === "FILL";
                const what = isFill
                  ? act === "BUY"
                    ? "Compra completada"
                    : "Venta completada"
                  : act === "HOLD"
                    ? "Esperar — sin operación"
                    : "Señal detectada — no se ejecutó";
                return (
                  <tr key={String(r.id)}>
                    <td className="tabular">{when(r.at as string)}</td>
                    <td>{String(r.symbol || "").replace("USDT", "")}</td>
                    <td>
                      <span
                        style={{
                          color: isFill
                            ? act === "BUY"
                              ? "var(--buy)"
                              : "var(--sell)"
                            : "var(--muted)",
                        }}
                      >
                        {isFill ? (act === "BUY" ? "▲ " : "▼ ") : "· "}
                        {what}
                      </span>
                    </td>
                    <td className="tabular">{price(r.price as number)}</td>
                    <td className="tabular">{r.qty == null ? "—" : qty(r.qty as number)}</td>
                    <td className="tabular">
                      {r.pnl == null ? "—" : money(r.pnl as number, { signed: true })}
                    </td>
                    <td>{statusLabel(String(r.state))}</td>
                    <td style={{ maxWidth: 280, whiteSpace: "normal" }}>
                      {reasonLabel(String(r.reason || ""))}
                    </td>
                  </tr>
                );
              })}
              {!historyRows.length && (
                <tr>
                  <td colSpan={8}>
                    <EmptyState
                      title="Historial vacío"
                      description="Todavía no hay compras, ventas ni señales en esta cuenta Demo."
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmDialog
        open={confirmStop}
        title="¿Detener el Bot Demo?"
        confirmLabel="Sí, detener"
        danger
        busy={busy}
        onCancel={() => setConfirmStop(false)}
        onConfirm={() => void doStop()}
      >
        <p>Al detener el bot:</p>
        <ul>
          <li>No abrirá compras nuevas.</li>
          <li>Cancelará entradas pendientes.</li>
          <li>Mantendrá las protecciones de las posiciones ya abiertas.</li>
        </ul>
        <p style={{ marginTop: 10 }}>
          Las protecciones dependen de que el servicio y el equipo sigan en marcha.
        </p>
      </ConfirmDialog>
    </div>
  );
}
