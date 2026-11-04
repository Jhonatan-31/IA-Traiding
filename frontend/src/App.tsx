import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";

const OverviewPage = lazy(() => import("./pages/OverviewPage"));
const MarketsPage = lazy(() => import("./pages/MarketsPage"));
const TradesPage = lazy(() => import("./pages/TradesPage"));
const StrategiesPage = lazy(() => import("./pages/StrategiesPage"));
const AiPage = lazy(() => import("./pages/AiPage"));
const RiskPage = lazy(() => import("./pages/RiskPage"));
const HealthPage = lazy(() => import("./pages/HealthPage"));
const ChartsPage = lazy(() => import("./pages/ChartsPage"));
const ProspectPage = lazy(() => import("./pages/ProspectPage"));
const AutoTradePage = lazy(() => import("./pages/AutoTradePage"));
const PerformancePage = lazy(() => import("./pages/PerformancePage"));
const ExpressPage = lazy(() => import("./pages/ExpressPage"));
const DemoAutoPage = lazy(() => import("./pages/DemoAutoPage"));
const PositionsPage = lazy(() => import("./pages/PositionsPage"));
const ConfigPage = lazy(() => import("./pages/ConfigPage"));

function PageLoader() {
  return (
    <div className="loading-block">
      <p className="muted">Cargando…</p>
    </div>
  );
}

export default function App() {
  return (
    <AppShell>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/mercado" element={<ChartsPage />} />
          <Route path="/movimientos" element={<TradesPage />} />
          <Route path="/posiciones" element={<PositionsPage />} />
          <Route path="/resultados" element={<PerformancePage />} />
          <Route path="/analisis-ia" element={<AiPage />} />
          <Route path="/seguridad" element={<RiskPage />} />
          <Route path="/sistema" element={<HealthPage />} />
          <Route path="/configuracion" element={<ConfigPage />} />
          <Route path="/demo" element={<DemoAutoPage />} />
          <Route path="/estrategias" element={<StrategiesPage />} />

          {/* Compatibilidad con rutas anteriores */}
          <Route path="/charts" element={<Navigate to="/mercado" replace />} />
          <Route path="/trades" element={<Navigate to="/movimientos" replace />} />
          <Route path="/performance" element={<Navigate to="/resultados" replace />} />
          <Route path="/ai" element={<Navigate to="/analisis-ia" replace />} />
          <Route path="/risk" element={<Navigate to="/seguridad" replace />} />
          <Route path="/health" element={<Navigate to="/sistema" replace />} />
          <Route path="/strategies" element={<Navigate to="/estrategias" replace />} />

          <Route path="/markets" element={<MarketsPage />} />
          <Route path="/prospect" element={<ProspectPage />} />
          <Route path="/auto-trade" element={<AutoTradePage />} />
          <Route path="/express" element={<ExpressPage />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
