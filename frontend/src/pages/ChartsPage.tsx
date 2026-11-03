import { useEffect, useMemo, useState } from "react";
import { api, fmtTime, type CandleResponse, type Position } from "../api";
import CandleChart from "../components/CandleChart";

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

const DEFAULT_TOGGLES: Record<string, boolean> = {
  sma10: true,
  sma20: false,
  sma50: true,
  sma200: false,
  ema9: false,
  ema21: false,
  ema50: false,
  bollinger: false,
  rsi: true,
  macd: true,
};

export default function ChartsPage() {
  const [symbol, setSymbol] = useState("ETHUSDT");
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>("1h");
  const [positions, setPositions] = useState<Position[]>([]);
  const [data, setData] = useState<CandleResponse | null>(null);
  const [toggles, setToggles] = useState(DEFAULT_TOGGLES);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void api.positions().then(setPositions).catch(() => undefined);
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await api.candles(symbol, interval, 300, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [symbol, interval]);

  const forming = data?.forming;
  const closedCount = data?.closed_count ?? 0;
  const options = useMemo(() => {
    const set = new Set(positions.map((p) => p.symbol));
    set.add("BTCUSDT");
    set.add("ETHUSDT");
    set.add(symbol);
    return Array.from(set).sort();
  }, [positions, symbol]);

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Gráficas avanzadas</h2>
          <p>
            OHLCV público Binance + indicadores server-side. La vela en formación
            se muestra pero no genera señales de trading.
          </p>
        </div>
        <button className="btn" onClick={() => void load()} disabled={loading}>
          {loading ? "Cargando…" : "Actualizar"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="actions" style={{ marginBottom: 14 }}>
        <select
          className="btn"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
        >
          {options.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          className="btn"
          style={{ width: 140 }}
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Símbolo"
        />
        {INTERVALS.map((iv) => (
          <button
            key={iv}
            className={`btn ${interval === iv ? "primary" : ""}`}
            onClick={() => setInterval(iv)}
          >
            {iv}
          </button>
        ))}
      </div>

      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Indicadores</h3>
        <div className="actions">
          {Object.keys(DEFAULT_TOGGLES).map((k) => (
            <button
              key={k}
              className={`btn ${toggles[k] ? "primary" : ""}`}
              onClick={() => setToggles((t) => ({ ...t, [k]: !t[k] }))}
            >
              {k}
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="actions" style={{ marginBottom: 10 }}>
          <span className="pill info">Cerradas: {closedCount}</span>
          <span className={`pill ${forming ? "warn" : "ok"}`}>
            {forming ? "Vela actual incompleta visible" : "Sin vela incompleta"}
          </span>
          <span className="pill info">Cache: {data?.cache ?? "—"}</span>
          <span className="muted">Actualizado: {fmtTime(data?.fetched_at)}</span>
        </div>
        {!data ? (
          <p className="muted">{loading ? "Cargando velas…" : "Sin datos"}</p>
        ) : (
          <CandleChart
            candles={data.candles}
            indicators={data.indicators}
            enabled={toggles}
            markers={data.trade_markers}
          />
        )}
        {data?.indicators?.rsi14 && (
          <p className="muted" style={{ marginTop: 10, fontSize: 12 }}>
            RSI14 último:{" "}
            {data.indicators.rsi14.filter((x) => x != null).at(-1) ?? "Sin datos"}{" "}
            · ATR14:{" "}
            {data.indicators.atr14?.filter((x) => x != null).at(-1) ?? "Sin datos"}{" "}
            · MACD:{" "}
            {data.indicators.macd?.macd.filter((x) => x != null).at(-1) ?? "Sin datos"}
          </p>
        )}
      </div>
    </div>
  );
}
