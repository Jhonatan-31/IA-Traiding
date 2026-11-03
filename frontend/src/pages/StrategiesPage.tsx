export default function StrategiesPage() {
  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Estrategias</h2>
          <p>Arquitectura preparada. Solo la referencia SMA está activa en paper.</p>
        </div>
      </div>
      <div className="card">
        <h3>SMA10 / SMA50 · 1h (referencia)</h3>
        <p>Estado: activa en simulación</p>
        <p>Versionado formal: pendiente</p>
        <p>Métricas fuera de muestra: Sin datos</p>
        <p>Benchmark buy & hold: Sin datos</p>
      </div>
      <div className="card" style={{ marginTop: 14 }}>
        <h3>Otras estrategias</h3>
        <p className="muted">
          No se activarán automáticamente sin pruebas. Placeholder para EMA, RSI,
          breakout, etc.
        </p>
      </div>
    </div>
  );
}
