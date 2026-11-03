import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, fmtNum, fmtTime, type CandleResponse, type Position } from "../api";
import CandleChart, { type Candle } from "../components/CandleChart";

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
const QUICK_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"] as const;

const DEFAULT_TOGGLES: Record<string, boolean> = {
  sma10: true,
  sma20: false,
  sma50: true,
  sma200: false,
  ema9: false,
  ema21: false,
  ema50: false,
  bollinger: false,
  rsi: false,
  macd: false,
};

type ConnState = "CONNECTED" | "RECONNECTING" | "STALE" | "DISCONNECTED";

type LiveMsg = {
  type: string;
  symbol?: string;
  interval?: string;
  candle_open_ms?: number;
  event_time_ms?: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  is_closed?: boolean;
  state?: ConnState;
  error?: string;
};

function wsUrl(symbol: string, interval: string) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const host = window.location.host;
  return `${proto}://${host}/ws/market?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`;
}

export default function ChartsPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>("1m");
  const [positions, setPositions] = useState<Position[]>([]);
  const [data, setData] = useState<CandleResponse | null>(null);
  const [liveCandle, setLiveCandle] = useState<Candle | null>(null);
  const [toggles, setToggles] = useState(DEFAULT_TOGGLES);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [conn, setConn] = useState<ConnState>("DISCONNECTED");
  const [liveFollow, setLiveFollow] = useState(true);
  const [lastEventMs, setLastEventMs] = useState<number | null>(null);
  const [msgCount, setMsgCount] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const lastOpenRef = useRef<number | null>(null);
  const lastEventRef = useRef<number | null>(null);

  useEffect(() => {
    void api.positions().then(setPositions).catch(() => undefined);
  }, []);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.candles(symbol, interval, 500, true);
      setData(payload);
      setLiveCandle(null);
      lastOpenRef.current = null;
      lastEventRef.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // WebSocket live stream (fan-out via market-stream)
  useEffect(() => {
    let stopped = false;
    let retry = 0;
    let timer: number | undefined;
    let staleTimer: number | undefined;

    function clearStale() {
      if (staleTimer) window.clearInterval(staleTimer);
      staleTimer = window.setInterval(() => {
        if (lastEventRef.current && Date.now() - lastEventRef.current > 15000) {
          setConn("STALE");
        }
      }, 3000);
    }

    function connect() {
      if (stopped) return;
      setConn("RECONNECTING");
      const ws = new WebSocket(wsUrl(symbol, interval));
      wsRef.current = ws;

      ws.onopen = () => {
        retry = 0;
        setConn("CONNECTED");
        ws.send(JSON.stringify({ action: "subscribe", symbol, interval }));
        clearStale();
      };

      ws.onmessage = (ev) => {
        let msg: LiveMsg;
        try {
          msg = JSON.parse(ev.data as string) as LiveMsg;
        } catch {
          return;
        }
        if (msg.type === "status" && msg.state) {
          setConn(msg.state);
          return;
        }
        if (msg.type === "error") {
          setError(msg.error || "ws_error");
          return;
        }
        if (msg.type !== "kline" && msg.type !== "snapshot") return;
        if (
          msg.candle_open_ms == null ||
          msg.open == null ||
          msg.high == null ||
          msg.low == null ||
          msg.close == null ||
          msg.volume == null
        ) {
          return;
        }
        const openMs = msg.candle_open_ms;
        const eventMs = msg.event_time_ms ?? openMs;
        // Reject out-of-order / stale
        if (lastOpenRef.current != null && openMs < lastOpenRef.current) return;
        if (
          lastOpenRef.current === openMs &&
          lastEventRef.current != null &&
          eventMs < lastEventRef.current
        ) {
          return;
        }
        lastOpenRef.current = openMs;
        lastEventRef.current = eventMs;
        setLastEventMs(eventMs);
        setMsgCount((n) => n + 1);
        setConn("CONNECTED");
        const candle: Candle = {
          open_time: openMs,
          open: msg.open,
          high: msg.high,
          low: msg.low,
          close: msg.close,
          volume: msg.volume,
          is_closed: Boolean(msg.is_closed),
        };
        setLiveCandle(candle);
        if (msg.is_closed) {
          // Soft refresh indicators/history after closed bar (does not drive trading)
          void api
            .candles(symbol, interval, 500, true)
            .then(setData)
            .catch(() => undefined);
        }
      };

      ws.onclose = () => {
        setConn("DISCONNECTED");
        if (stopped) return;
        retry += 1;
        const wait = Math.min(30000, 800 * 2 ** Math.min(retry, 5));
        timer = window.setTimeout(connect, wait);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      if (staleTimer) window.clearInterval(staleTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [symbol, interval]);

  const options = useMemo(() => {
    const set = new Set<string>([...QUICK_SYMBOLS]);
    positions.forEach((p) => set.add(p.symbol));
    set.add(symbol);
    return Array.from(set).sort();
  }, [positions, symbol]);

  const lastPrice = liveCandle?.close ?? data?.candles?.at(-1)?.close ?? null;
  const openPos = positions.filter((p) => p.symbol === symbol);

  function toggleFullscreen() {
    const el = wrapRef.current;
    if (!el) return;
    if (!document.fullscreenElement) void el.requestFullscreen();
    else void document.exitFullscreen();
  }

  const connPill =
    conn === "CONNECTED" ? "ok" : conn === "STALE" || conn === "RECONNECTING" ? "warn" : "err";

  return (
    <div ref={wrapRef} style={{ background: "#0b1018", minHeight: "100%" }}>
      <div className="page-title">
        <div>
          <h2>Terminal de gráficas</h2>
          <p>
            Lightweight Charts v4 · historial REST + vivo vía market-stream (Binance público).
            La vela abierta es solo visualización; SMA/Shadow/Lab usan velas cerradas.
          </p>
        </div>
        <div className="actions">
          <button className="btn" onClick={() => void loadHistory()} disabled={loading}>
            {loading ? "Cargando…" : "Recargar historial"}
          </button>
          <button
            className={`btn ${liveFollow ? "primary" : ""}`}
            onClick={() => setLiveFollow((v) => !v)}
          >
            {liveFollow ? "Seguir vivo: ON" : "Seguir vivo: OFF"}
          </button>
          <button className="btn" onClick={toggleFullscreen}>
            Pantalla completa
          </button>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="actions" style={{ flexWrap: "wrap" }}>
          {QUICK_SYMBOLS.map((s) => (
            <button
              key={s}
              className={`btn ${symbol === s ? "primary" : ""}`}
              onClick={() => setSymbol(s)}
            >
              {s}
            </button>
          ))}
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
          {INTERVALS.map((iv) => (
            <button
              key={iv}
              className={`btn ${interval === iv ? "primary" : ""}`}
              onClick={() => setInterval(iv)}
            >
              {iv}
            </button>
          ))}
          <span className={`pill ${connPill}`}>{conn}</span>
          <span className="pill info">
            {symbol} · {interval}
          </span>
          <span className="pill info">
            Precio: {lastPrice == null ? "—" : fmtNum(lastPrice, 4)}
          </span>
          <span className="muted" style={{ fontSize: 12 }}>
            WS msgs: {msgCount}
            {lastEventMs ? ` · evt ${new Date(lastEventMs).toISOString()}` : ""}
          </span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <h3>Indicadores (display)</h3>
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
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          No modifican el motor SMA de producción. RSI/MACD paneles sincronizados al
          rango visible.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="actions" style={{ marginBottom: 10 }}>
          <span className="pill info">Cerradas: {data?.closed_count ?? "—"}</span>
          <span className={`pill ${liveCandle && !liveCandle.is_closed ? "warn" : "ok"}`}>
            {liveCandle && !liveCandle.is_closed
              ? "Vela abierta (live)"
              : "Esperando vela live"}
          </span>
          <span className="pill info">Cache REST: {data?.cache ?? "—"}</span>
          <span className="muted">Historial: {fmtTime(data?.fetched_at)}</span>
        </div>
        {!data ? (
          <p className="muted">{loading ? "Cargando velas…" : "Sin datos"}</p>
        ) : (
          <CandleChart
            candles={data.candles}
            liveCandle={liveCandle}
            indicators={data.indicators}
            enabled={toggles}
            markers={data.trade_markers}
            liveFollow={liveFollow}
            onUserScrollAway={() => setLiveFollow(false)}
          />
        )}
      </div>

      {openPos.length > 0 && (
        <div className="card">
          <h3>Posiciones SMA paper ({symbol})</h3>
          <p className="muted" style={{ fontSize: 12 }}>
            Ledger SMA separado de Lab/Shadow. Solo referencia visual.
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Qty</th>
                  <th>Entrada</th>
                  <th>Mark</th>
                  <th>uPnL</th>
                </tr>
              </thead>
              <tbody>
                {openPos.map((p) => (
                  <tr key={p.symbol}>
                    <td>{fmtNum(p.qty, 6)}</td>
                    <td>{fmtNum(p.cost / (p.qty || 1), 4)}</td>
                    <td>{fmtNum(p.price, 4)}</td>
                    <td>{fmtNum(p.unrealized_pnl, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
