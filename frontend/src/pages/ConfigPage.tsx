import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { METRIC_HELP } from "../ui/labels";

export default function ConfigPage() {
  return (
    <div>
      <PageHeader
        title="Configuración"
        subtitle="Ajustes visibles y accesos a herramientas avanzadas. El trading real permanece desactivado."
      />
      <div className="panel" style={{ marginBottom: 14 }}>
        <h3 style={{ marginTop: 0, color: "var(--text)" }}>Modo de operación</h3>
        <p className="muted" style={{ lineHeight: 1.5 }}>
          {METRIC_HELP.paper} El sistema opera solo en modo PAPER_ONLY.
        </p>
        <ul className="muted" style={{ lineHeight: 1.7 }}>
          <li>Trading real: desactivado</li>
          <li>Operaciones con IA automática real: desactivadas</li>
          <li>Mercado de referencia: Binance Spot (precios)</li>
        </ul>
      </div>
      <div className="grid stats">
        <Link to="/demo" className="card">
          <h3>Bot Demo</h3>
          <p className="muted">Iniciar y detener el bot de demostración.</p>
        </Link>
        <Link to="/auto-trade" className="card">
          <h3>Bot Automático</h3>
          <p className="muted">Cuenta de laboratorio (avanzado).</p>
        </Link>
        <Link to="/strategies" className="card">
          <h3>Estrategias</h3>
          <p className="muted">Parámetros y perfiles (lectura / avanzado).</p>
        </Link>
        <Link to="/express" className="card">
          <h3>Prueba Express</h3>
          <p className="muted">Ensayo cronometrado de investigación.</p>
        </Link>
      </div>
    </div>
  );
}
