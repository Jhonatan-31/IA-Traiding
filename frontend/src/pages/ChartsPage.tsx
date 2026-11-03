import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  fmtNum,
  fmtTime,
  type CandleResponse,
  type ChartMarker,
  type ChartPositionOverlay,
  type Position,
} from "../api";
import CandleChart, { type Candle, type LiveChartApi } from "../components/CandleChart";
import {
  mergeCandles,
  shouldApplyLive,
  type CandleBar,
} from "../charts/candleState";

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
  atr: false,
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
  source?: string;
  hub_recv_ms?: number;
  server_send_ms?: number;
  binance_to_hub_ms?: number | null;
  hub_internal_ms?: number | null;
  last_trade_time_ms?: number;
  trade_count?: number;
};

type PendingTick = LiveMsg & {
  browser_recv_perf: number;
  browser_recv_wall: number;
};

function wsUrl(symbol: string, interval: string) {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws/market?symbol=${encodeURIComponent(symbol)}&interval=${encodeURIComponent(interval)}`;
}

export default function ChartsPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>("1m");
  const [positions, setPositions] = useState<Position[]>([]);
  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [indicators, setIndicators] = useState<CandleResponse["indicators"]>();
  const [indicatorsMeta, setIndicatorsMeta] =
    useState<CandleResponse["indicators_meta"]>();
  const [markers, setMarkers] = useState<ChartMarker[]>([]);
  const [overlays, setOverlays] = useState<ChartPositionOverlay[]>([]);
  const [meta, setMeta] = useState<{ cache?: string; fetched_at?: string; closed?: number }>(
    {}
  );
  const [liveCandle, setLiveCandle] = useState<Candle | null>(null);
  const [toggles, setToggles] = useState(DEFAULT_TOGGLES);
  const [markerFilters, setMarkerFilters] = useState({
    sma: true,
    lab: true,
    shadow: true,
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [historyEnd, setHistoryEnd] = useState(false);
  const [conn, setConn] = useState<ConnState>("DISCONNECTED");
  const [liveFollow, setLiveFollow] = useState(true);
  const [lastEventMs, setLastEventMs] = useState<number | null>(null);
  const [msgCount, setMsgCount] = useState(0);
  const [latUi, setLatUi] = useState<{
    binanceHub: number | null;
    hubInternal: number | null;
    browserPaint: number | null;
    tradeAge: number | null;
    clockSkew: number | null;
    tradeTime: number | null;
    source: string;
    p50: number | null;
    p95: number | null;
    p99: number | null;
  }>({
    binanceHub: null,
    hubInternal: null,
    browserPaint: null,
    tradeAge: null,
    clockSkew: null,
    tradeTime: null,
    source: "—",
    p50: null,
    p95: null,
    p99: null,
  });
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const lastOpenRef = useRef<number | null>(null);
  const lastEventRef = useRef<number | null>(null);
  const goLiveRef = useRef<(() => void) | null>(null);
  const liveApiRef = useRef<LiveChartApi | null>(null);
  const candlesCacheRef = useRef<Map<string, CandleBar[]>>(new Map());
  const liveFollowRef = useRef(liveFollow);
  liveFollowRef.current = liveFollow;
  const pendingTickRef = useRef<PendingTick | null>(null);
  const rafRef = useRef<number>(0);
  const tickCountRef = useRef(0);
  const priceFlashRef = useRef<HTMLSpanElement | null>(null);
  const lastPriceRef = useRef<number | null>(null);
  const paintSamplesRef = useRef<number[]>([]);
  const lastUiPushRef = useRef(0);

  function pct(samples: number[], p: number): number | null {
    if (!samples.length) return null;
    const xs = [...samples].sort((a, b) => a - b);
    const i = Math.min(
      xs.length - 1,
      Math.max(0, Math.round((p / 100) * (xs.length - 1)))
    );
    return xs[i];
  }

  const resetKey = `${symbol}:${interval}`;

  useEffect(() => {
    void api.positions().then(setPositions).catch(() => undefined);
  }, []);

  const applyPayload = useCallback(
    (payload: CandleResponse, mode: "replace" | "prepend" | "append") => {
      setMarkers((payload.markers || payload.trade_markers || []) as ChartMarker[]);
      setOverlays((payload.position_overlays || []) as ChartPositionOverlay[]);
      setIndicators(payload.indicators);
      setIndicatorsMeta(payload.indicators_meta);
      setMeta({
        cache: payload.cache,
        fetched_at: payload.fetched_at,
        closed: payload.closed_count,
      });
      setCandles((prev) => {
        const next = mergeCandles(prev, payload.candles, mode);
        candlesCacheRef.current.set(resetKey, next);
        return next;
      });
      if (payload.history_cursor && payload.history_cursor.has_more === false) {
        setHistoryEnd(true);
      }
    },
    [resetKey]
  );

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);
    setHistoryEnd(false);
    setLiveCandle(null);
    lastOpenRef.current = null;
    lastEventRef.current = null;
    try {
      const cached = candlesCacheRef.current.get(resetKey);
      if (cached?.length) {
        setCandles(cached);
      } else {
        setCandles([]);
      }
      const payload = await api.candles(symbol, interval, 500, true);
      setCandles([]);
      applyPayload(payload, "replace");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
      setCandles([]);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, resetKey, applyPayload]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const loadOlder = useCallback(async () => {
    if (loadingOlder || historyEnd || candles.length === 0) return;
    setLoadingOlder(true);
    try {
      const end = candles[0].open_time - 1;
      const payload = await api.candles(symbol, interval, 400, true, end);
      if (!payload.candles.length) {
        setHistoryEnd(true);
        return;
      }
      const before = candles.length;
      applyPayload(payload, "prepend");
      // if no growth after dedupe → end
      setTimeout(() => {
        setCandles((cur) => {
          if (cur.length <= before) setHistoryEnd(true);
          return cur;
        });
      }, 0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error historial");
    } finally {
      setLoadingOlder(false);
    }
  }, [loadingOlder, historyEnd, candles, symbol, interval, applyPayload]);

  // WebSocket live — trade ticks via rAF (no React re-render per trade)
  useEffect(() => {
    let stopped = false;
    let retry = 0;
    let timer: number | undefined;
    let staleTimer: number | undefined;
    let uiTimer: number | undefined;

    function clearStale() {
      if (staleTimer) window.clearInterval(staleTimer);
      staleTimer = window.setInterval(() => {
        if (lastEventRef.current && Date.now() - lastEventRef.current > 5000) {
          setConn("STALE");
        }
      }, 1000);
    }

    function flushTick() {
      rafRef.current = 0;
      const msg = pendingTickRef.current;
      if (!msg || msg.candle_open_ms == null) return;
      const paintAt = performance.now();
      const browserPaint =
        paintAt >= msg.browser_recv_perf ? paintAt - msg.browser_recv_perf : null;
      const candle: Candle = {
        open_time: msg.candle_open_ms,
        open: msg.open!,
        high: msg.high!,
        low: msg.low!,
        close: msg.close!,
        volume: msg.volume!,
        is_closed: Boolean(msg.is_closed),
      };
      liveApiRef.current?.applyLive(candle);
      lastPriceRef.current = candle.close;
      if (priceFlashRef.current) {
        priceFlashRef.current.textContent = fmtNum(candle.close, 4);
        priceFlashRef.current.dataset.dir =
          candle.close >= candle.open ? "up" : "down";
      }
      const binanceHub =
        msg.binance_to_hub_ms != null && msg.binance_to_hub_ms >= 0
          ? msg.binance_to_hub_ms
          : null;
      const hubInternal =
        msg.hub_internal_ms != null && msg.hub_internal_ms >= 0
          ? msg.hub_internal_ms
          : null;
      // Wall delta server_send→browser: estimate clock skew, NOT hop latency
      const clockSkew =
        msg.server_send_ms != null
          ? msg.browser_recv_wall - msg.server_send_ms
          : null;
      const tradeTs = msg.last_trade_time_ms ?? msg.event_time_ms ?? null;
      const tradeAge =
        tradeTs != null ? Math.max(0, msg.browser_recv_wall - tradeTs) : null;
      if (browserPaint != null && browserPaint < 2000) {
        paintSamplesRef.current.push(browserPaint);
        if (paintSamplesRef.current.length > 300) {
          paintSamplesRef.current = paintSamplesRef.current.slice(-300);
        }
      }
      const now = Date.now();
      if (now - lastUiPushRef.current > 100) {
        lastUiPushRef.current = now;
        setLatUi({
          binanceHub,
          hubInternal,
          browserPaint,
          tradeAge,
          clockSkew,
          tradeTime: tradeTs,
          source: msg.source || msg.type,
          p50: pct(paintSamplesRef.current, 50),
          p95: pct(paintSamplesRef.current, 95),
          p99: pct(paintSamplesRef.current, 99),
        });
        setLiveCandle(candle);
        setLastEventMs(msg.event_time_ms ?? msg.candle_open_ms);
        setMsgCount(tickCountRef.current);
      }
    }

    function scheduleTick(msg: LiveMsg) {
      pendingTickRef.current = {
        ...msg,
        browser_recv_perf: performance.now(),
        browser_recv_wall: Date.now(),
      };
      if (!rafRef.current) {
        rafRef.current = window.requestAnimationFrame(flushTick);
      }
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
        if (
          msg.type !== "kline" &&
          msg.type !== "snapshot" &&
          msg.type !== "candle_tick"
        ) {
          return;
        }
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
        const live = {
          candle_open_ms: msg.candle_open_ms,
          event_time_ms: msg.event_time_ms,
          open: msg.open,
          high: msg.high,
          low: msg.low,
          close: msg.close,
          volume: msg.volume,
          is_closed: Boolean(msg.is_closed),
        };
        if (!shouldApplyLive(lastOpenRef.current, lastEventRef.current, live)) {
          return;
        }
        lastOpenRef.current = live.candle_open_ms;
        lastEventRef.current = live.event_time_ms ?? live.candle_open_ms;
        tickCountRef.current += 1;
        setConn("CONNECTED");
        scheduleTick(msg);

        if (msg.is_closed || msg.type === "kline") {
          // Throttle overlay mark update on close only
          setOverlays((prev) =>
            prev.map((o) => ({
              ...o,
              mark_price: live.close,
              unrealized_pnl:
                o.entry_price != null
                  ? (live.close - o.entry_price) * o.qty
                  : o.unrealized_pnl,
            }))
          );
          if (msg.is_closed) {
            void api
              .candles(symbol, interval, 500, true)
              .then((p) => {
                applyPayload(p, liveFollowRef.current ? "replace" : "append");
                setLiveCandle(null);
              })
              .catch(() => undefined);
          }
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
      if (uiTimer) window.clearInterval(uiTimer);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [symbol, interval, applyPayload]);

  const options = useMemo(() => {
    const set = new Set<string>([...QUICK_SYMBOLS]);
    positions.forEach((p) => set.add(p.symbol));
    set.add(symbol);
    return Array.from(set).sort();
  }, [positions, symbol]);

  const lastPrice = liveCandle?.close ?? candles.at(-1)?.close ?? null;
  const symbolOverlays = overlays.filter((o) => o.symbol === symbol);

  function toggleFullscreen() {
    const el = wrapRef.current;
    if (!el) return;
    if (!document.fullscreenElement) void el.requestFullscreen();
    else void document.exitFullscreen();
  }

  function goRealtime() {
    setLiveFollow(true);
    goLiveRef.current?.();
  }

  const connPill =
    conn === "CONNECTED"
      ? "ok"
      : conn === "STALE" || conn === "RECONNECTING"
        ? "warn"
        : "err";

  const tradesTable = markers
    .filter((m) => markerAllowedUi(m, markerFilters))
    .slice()
    .reverse()
    .slice(0, 40);

  return (
    <div ref={wrapRef} style={{ background: "#0b1018", minHeight: "100%" }}>
      <div className="page-title">
        <div>
          <h2>Terminal de gráficas</h2>
          <p>
            Lightweight Charts v4 · REST historial + WS market-stream. Predicciones Shadow ≠
            ejecuciones. PAPER_ONLY.
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
          <button className="btn primary" onClick={goRealtime}>
            Volver al tiempo real
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
          <span
            className={`pill ${liveCandle && !liveCandle.is_closed ? "ok" : "info"}`}
            title="Actualización por trade stream"
          >
            LIVE
          </span>
          <span className="pill info">
            Precio:{" "}
            <span
              ref={priceFlashRef}
              style={{
                fontVariantNumeric: "tabular-nums",
                color:
                  liveCandle && liveCandle.close >= liveCandle.open
                    ? "#26a69a"
                    : liveCandle
                      ? "#ef5350"
                      : undefined,
              }}
            >
              {lastPrice == null ? "—" : fmtNum(lastPrice, 4)}
            </span>
          </span>
          <span className="muted" style={{ fontSize: 12 }}>
            ticks: {msgCount}
            {latUi.tradeTime
              ? ` · trade ${new Date(latUi.tradeTime).toISOString()}`
              : lastEventMs
                ? ` · evt ${new Date(lastEventMs).toISOString()}`
                : ""}
            {` · src ${latUi.source}`}
            {latUi.binanceHub != null
              ? ` · B→hub ${Math.round(latUi.binanceHub)}ms`
              : ""}
            {latUi.hubInternal != null
              ? ` · hubΔ ${Math.round(latUi.hubInternal)}ms`
              : ""}
            {latUi.browserPaint != null
              ? ` · paint ${Math.round(latUi.browserPaint)}ms`
              : ""}
            {latUi.tradeAge != null
              ? ` · age ${Math.round(latUi.tradeAge)}ms`
              : ""}
            {latUi.clockSkew != null
              ? ` · skew~${Math.round(latUi.clockSkew)}ms`
              : ""}
            {latUi.p50 != null
              ? ` · paint p50/95/99 ${Math.round(latUi.p50)}/${Math.round(latUi.p95 ?? 0)}/${Math.round(latUi.p99 ?? 0)}`
              : ""}
            {loadingOlder ? " · cargando historial…" : ""}
            {historyEnd ? " · fin historial" : ""}
            {` · bars ${candles.length}`}
          </span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <h3>Marcadores por ledger</h3>
        <div className="actions">
          {(
            [
              ["sma", "SMA ejecuciones"],
              ["lab", "Lab ejecuciones"],
              ["shadow", "Shadow predicciones"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              className={`btn ${markerFilters[k] ? "primary" : ""}`}
              onClick={() =>
                setMarkerFilters((f) => ({ ...f, [k]: !f[k] }))
              }
            >
              {label}
            </button>
          ))}
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Círculos morados = predicción Shadow (no fill). Flechas = ejecuciones paper.
        </p>
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
          No modifican el motor SMA de producción. RSI/MACD/ATR sincronizados al rango.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="actions" style={{ marginBottom: 10 }}>
          <span className="pill info">Cerradas: {meta.closed ?? "—"}</span>
          <span className={`pill ${liveCandle && !liveCandle.is_closed ? "warn" : "ok"}`}>
            {liveCandle && !liveCandle.is_closed
              ? "Vela abierta (live)"
              : "Esperando vela live"}
          </span>
          <span className="pill info">Cache REST: {meta.cache ?? "—"}</span>
          <span className="muted">Historial: {fmtTime(meta.fetched_at)}</span>
        </div>
        {!candles.length ? (
          <p className="muted">{loading ? "Cargando velas…" : "Sin datos"}</p>
        ) : (
          <CandleChart
            resetKey={resetKey}
            candles={candles}
            liveCandle={null}
            indicators={indicators}
            indicatorsPreliminary={Boolean(indicatorsMeta?.last_bar_preliminary)}
            enabled={toggles}
            markers={markers}
            markerFilters={markerFilters}
            positions={symbolOverlays}
            liveFollow={liveFollow}
            onUserScrollAway={() => setLiveFollow(false)}
            onNeedOlder={() => void loadOlder()}
            onGoLiveReady={(fn) => {
              goLiveRef.current = fn;
            }}
            onLiveApi={(api) => {
              liveApiRef.current = api;
            }}
          />
        )}
      </div>

      {symbolOverlays.length > 0 && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h3>Posiciones abiertas ({symbol})</h3>
          <p className="muted" style={{ fontSize: 12 }}>
            Ledgers separados. SL/TP solo cuando existen en DB (Lab).
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))",
              gap: 12,
            }}
          >
            {symbolOverlays.map((p) => (
              <div
                key={p.ledger}
                style={{
                  border: "1px solid #2a3a55",
                  borderRadius: 8,
                  padding: 12,
                  background: "#0e141d",
                }}
              >
                <div className="actions" style={{ marginBottom: 8 }}>
                  <span className="pill info">{p.ledger.toUpperCase()}</span>
                  <span className="pill">{p.symbol}</span>
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.6 }}>
                  <div>Qty: {fmtNum(p.qty, 6)}</div>
                  <div>Entrada: {fmtNum(p.entry_price, 4)}</div>
                  <div>Mark: {fmtNum(p.mark_price, 4)}</div>
                  <div>uPnL: {fmtNum(p.unrealized_pnl, 4)}</div>
                  <div>SL: {p.stop_loss_price == null ? "—" : fmtNum(p.stop_loss_price, 4)}</div>
                  <div>TP: {p.take_profit_price == null ? "—" : fmtNum(p.take_profit_price, 4)}</div>
                  <div>
                    Restante:{" "}
                    {p.bars_remaining == null
                      ? "—"
                      : `${p.bars_remaining}/${p.max_hold_bars ?? "?"} barras`}
                  </div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {p.opened_at ? `Desde ${fmtTime(p.opened_at)}` : p.note}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h3>Operaciones / predicciones visibles</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Ledger</th>
                <th>Tipo</th>
                <th>Side</th>
                <th>At</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Strategy</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {tradesTable.map((m) => (
                <tr key={`${m.ledger}-${m.source}-${m.id}`}>
                  <td>{m.ledger || m.source}</td>
                  <td>
                    {m.kind === "prediction" ? (
                      <span className="pill warn">predicción</span>
                    ) : (
                      <span className="pill ok">ejecución</span>
                    )}
                  </td>
                  <td>{m.side}</td>
                  <td>{fmtTime(m.at)}</td>
                  <td>{m.price == null ? "—" : fmtNum(m.price, 4)}</td>
                  <td>{m.qty == null ? "—" : fmtNum(m.qty, 6)}</td>
                  <td>{m.strategy || "—"}</td>
                  <td>{m.reason || "—"}</td>
                </tr>
              ))}
              {!tradesTable.length && (
                <tr>
                  <td colSpan={8} className="muted">
                    Sin marcadores para filtros/símbolo actuales
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function markerAllowedUi(
  m: ChartMarker,
  f: { sma: boolean; lab: boolean; shadow: boolean }
) {
  const ledger = (m.ledger || m.source || "sma").toLowerCase();
  if (ledger.includes("lab")) return f.lab;
  if (
    ledger.includes("shadow") ||
    ledger.includes("prospect") ||
    ledger.includes("ml") ||
    m.kind === "prediction"
  )
    return f.shadow;
  return f.sma;
}
