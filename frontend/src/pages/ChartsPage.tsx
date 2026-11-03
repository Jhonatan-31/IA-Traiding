export default function ChartsPage() {
  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Gráficas avanzadas</h2>
          <p>OHLCV + indicadores. Requiere endpoint de velas (Etapa D).</p>
        </div>
      </div>
      <div className="card">
        <p className="muted">
          Sin datos de velas expuestos aún por la API. No se fabrican series. Próximo
          paso: endpoint /api/candles/:symbol con SMA/EMA/RSI/MACD calculados sin look-ahead.
        </p>
      </div>
    </div>
  );
}
