import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { MetricCard } from "../components/ui/MetricCard";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { money, when } from "../ui/format";

const TOKEN_KEY = "lab_control_token";

type Strat = Record<string, unknown>;

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strat[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) || "");
  const [confirmStop, setConfirmStop] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.activeStrategies();
      setStrategies(r.strategies || []);
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

  return (
    <div>
      <PageHeader
        eyebrow="Etapa T"
        title="Estrategias de Trading"
        subtitle="Tres políticas independientes en simulación. La Conservadora es el Bot Demo actual; Trading Activo usa una cartera nueva; la IA solo observa."
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
          ? `${String(last.action || "")} · ${String(last.symbol || "").replace("USDT", "")} · ${when(String(last.at || ""))}`
          : "—"}
      </p>
      <p className="muted" style={{ fontSize: 12, lineHeight: 1.4 }}>
        Motivo: {String(s?.last_reason_human || "—")}
      </p>
      <div style={{ marginTop: 14 }}>{props.footer}</div>
    </div>
  );
}
