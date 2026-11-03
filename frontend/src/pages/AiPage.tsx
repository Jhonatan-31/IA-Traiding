export default function AiPage() {
  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Inteligencia artificial</h2>
          <p>Módulo de investigación. Sin predicciones inventadas.</p>
        </div>
      </div>
      <div className="card">
        <h3>Estado del modelo</h3>
        <p>
          <span className="pill warn">Modelo no disponible</span>
        </p>
        <p className="muted" style={{ marginTop: 12 }}>
          Aún no hay entrenamiento reproducible, walk-forward ni calibración. La
          Etapa E construirá el pipeline baseline (features OHLCV + validación
          cronológica) antes de mostrar probabilidades.
        </p>
      </div>
    </div>
  );
}
