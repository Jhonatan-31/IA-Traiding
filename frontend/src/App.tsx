import { Suspense, lazy } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const MarketsPage = lazy(() => import("./pages/MarketsPage"));
const TradesPage = lazy(() => import("./pages/TradesPage"));
const StrategiesPage = lazy(() => import("./pages/StrategiesPage"));
const AiPage = lazy(() => import("./pages/AiPage"));
const RiskPage = lazy(() => import("./pages/RiskPage"));
const HealthPage = lazy(() => import("./pages/HealthPage"));
const ChartsPage = lazy(() => import("./pages/ChartsPage"));

const links = [
  { to: "/", label: "Resumen" },
  { to: "/markets", label: "Mercados" },
  { to: "/charts", label: "Gráficas" },
  { to: "/trades", label: "Operaciones" },
  { to: "/strategies", label: "Estrategias" },
  { to: "/ai", label: "Inteligencia artificial" },
  { to: "/risk", label: "Gestión de riesgo" },
  { to: "/health", label: "System Health" },
];

function PageLoader() {
  return <p className="muted">Cargando módulo…</p>;
}

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>AI Trading Bot Pro</h1>
          <p>PAPER ONLY · Binance Spot</p>
        </div>
        <nav className="nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          Simulación virtual. Sin claves privadas ni órdenes reales. No garantiza
          ganancias.
        </div>
      </aside>
      <main className="content">
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/markets" element={<MarketsPage />} />
            <Route path="/charts" element={<ChartsPage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/strategies" element={<StrategiesPage />} />
            <Route path="/ai" element={<AiPage />} />
            <Route path="/risk" element={<RiskPage />} />
            <Route path="/health" element={<HealthPage />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}
