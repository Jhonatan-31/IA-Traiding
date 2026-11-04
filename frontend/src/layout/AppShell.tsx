import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api";
import { StatusBadge } from "../components/ui/StatusBadge";
import { when } from "../ui/format";

type NavItem = { to: string; label: string; icon: string; end?: boolean; group?: string };

const PRIMARY: NavItem[] = [
  { to: "/", label: "Inicio", icon: "◈", end: true },
  { to: "/mercado", label: "Mercado en vivo", icon: "▣" },
  { to: "/demo", label: "Bot Demo", icon: "▶" },
  { to: "/estrategias", label: "Estrategias", icon: "⬡︎" },
  { to: "/movimientos", label: "Movimientos", icon: "⇄" },
  { to: "/posiciones", label: "Mis posiciones", icon: "◎" },
  { to: "/resultados", label: "Resultados", icon: "▦" },
];

const SECONDARY: NavItem[] = [
  { to: "/analisis-ia", label: "Análisis IA", icon: "◇" },
  { to: "/seguridad", label: "Seguridad", icon: "⬡" },
  { to: "/sistema", label: "Estado del sistema", icon: "◌" },
  { to: "/configuracion", label: "Configuración", icon: "⚙" },
];

const TITLE: Record<string, string> = {
  "/": "Inicio",
  "/mercado": "Mercado en vivo",
  "/charts": "Mercado en vivo",
  "/markets": "Mercados",
  "/demo": "Bot Demo",
  "/estrategias": "Estrategias de Trading",
  "/strategies": "Estrategias de Trading",
  "/movimientos": "Movimientos",
  "/trades": "Movimientos",
  "/posiciones": "Mis posiciones",
  "/resultados": "Resultados",
  "/performance": "Resultados",
  "/analisis-ia": "Análisis de Inteligencia Artificial",
  "/ai": "Análisis de Inteligencia Artificial",
  "/seguridad": "Seguridad y protección",
  "/risk": "Seguridad y protección",
  "/sistema": "Estado del sistema",
  "/health": "Estado del sistema",
  "/configuracion": "Configuración",
  "/auto-trade": "Bot Automático",
  "/express": "Prueba Express",
  "/prospect": "Análisis prospectivo",
};

export function AppShell(props: { children: ReactNode }) {
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [demoStatus, setDemoStatus] = useState<string | null>(null);
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [lastPulse, setLastPulse] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function pulse() {
      try {
        const [d, h] = await Promise.all([
          api.demoStatus().catch(() => null),
          api.health().catch(() => null),
        ]);
        if (!alive) return;
        if (d) {
          setDemoStatus(String(d.bot_status || ""));
          const st = d.state as Record<string, unknown> | undefined;
          setLastPulse(String(st?.heartbeat_at || st?.last_eval_at || ""));
        }
        setHealthOk(h != null);
      } catch {
        if (alive) setHealthOk(false);
      }
    }
    void pulse();
    const id = setInterval(() => void pulse(), 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [loc.pathname]);

  const title = TITLE[loc.pathname] || "AI Trading Bot Pro";
  const running = demoStatus === "RUNNING";

  return (
    <div className={`app-shell${collapsed ? " is-collapsed" : ""}${mobileOpen ? " is-mobile-open" : ""}`}>
      <aside className="sidebar" aria-label="Navegación principal">
        <div className="brand">
          <div className="brand-mark" aria-hidden>
            AT
          </div>
          {!collapsed && (
            <div>
              <h1>AI Trading Bot Pro</h1>
              <p>Simulación · Binance Spot</p>
            </div>
          )}
        </div>

        <div className="sidebar-status">
          <StatusBadge variant={healthOk === false ? "danger" : "ok"} pulse={running}>
            {healthOk === false ? "Sin conexión" : "Conectado"}
          </StatusBadge>
          {!collapsed && (
            <StatusBadge variant={running ? "ok" : "warn"}>
              Bot Demo · {running ? "En marcha" : "Detenido"}
            </StatusBadge>
          )}
        </div>

        <nav className="nav">
          <p className="nav-group">{collapsed ? "·" : "Principal"}</p>
          {PRIMARY.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              title={l.label}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              <span className="nav-icon" aria-hidden>
                {l.icon}
              </span>
              {!collapsed && <span>{l.label}</span>}
            </NavLink>
          ))}
          <p className="nav-group">{collapsed ? "·" : "Más"}</p>
          {SECONDARY.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              title={l.label}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              <span className="nav-icon" aria-hidden>
                {l.icon}
              </span>
              {!collapsed && <span>{l.label}</span>}
            </NavLink>
          ))}
        </nav>

        {!collapsed && (
          <div className="sidebar-foot">
            <strong>Modo SIMULACIÓN</strong>
            <span>No se opera con dinero real. Las operaciones son virtuales con fines de demostración.</span>
            <NavLink to="/demo" className="quick-demo">
              Ir al Bot Demo →
            </NavLink>
          </div>
        )}

        <button
          type="button"
          className="sidebar-toggle"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expandir menú" : "Contraer menú"}
        >
          {collapsed ? "»" : "«"}
        </button>
      </aside>

      <div className="shell-main">
        <header className="topbar">
          <button
            type="button"
            className="mobile-menu-btn"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Abrir menú"
          >
            ☰
          </button>
          <div className="topbar-title">
            <h2>{title}</h2>
            <p className="sim-banner">SIMULACIÓN · sin dinero real</p>
          </div>
          <div className="topbar-meta">
            <StatusBadge variant="info">SIMULACIÓN</StatusBadge>
            <StatusBadge variant={running ? "ok" : "neutral"}>
              {running ? "Bot activo" : "Bot detenido"}
            </StatusBadge>
            <span className="topbar-time tabular" title="Última conexión del servicio">
              {lastPulse ? `Act. ${when(lastPulse, { withDate: false })}` : "—"}
            </span>
            <NavLink to="/configuracion" className="topbar-gear" title="Configuración">
              ⚙
            </NavLink>
          </div>
        </header>
        <main className="content">{props.children}</main>
      </div>

      {mobileOpen ? (
        <button
          type="button"
          className="sidebar-scrim"
          aria-label="Cerrar menú"
          onClick={() => setMobileOpen(false)}
        />
      ) : null}
    </div>
  );
}
