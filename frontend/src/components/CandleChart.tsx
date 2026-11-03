import { useEffect, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LogicalRange,
  type MouseEventParams,
  type UTCTimestamp,
} from "lightweight-charts";

export type Candle = {
  open_time: number;
  close_time?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_closed?: boolean;
};

export type TradeMarker = {
  id: number;
  side: string;
  price: number | null;
  candle_ms: number;
  at: string | null;
  source?: string;
  ledger?: string;
  kind?: string;
  qty?: number | null;
  strategy?: string | null;
  reason?: string | null;
  label?: string;
};

export type PositionOverlay = {
  ledger: string;
  symbol: string;
  qty: number;
  entry_price: number | null;
  mark_price: number | null;
  unrealized_pnl: number | null;
  stop_loss_price: number | null;
  take_profit_price: number | null;
  opened_at?: string | null;
  bars_remaining?: number | null;
  max_hold_bars?: number | null;
  note?: string;
};

export type IndicatorPack = {
  sma10?: (number | null)[];
  sma20?: (number | null)[];
  sma50?: (number | null)[];
  sma200?: (number | null)[];
  ema9?: (number | null)[];
  ema21?: (number | null)[];
  ema50?: (number | null)[];
  rsi14?: (number | null)[];
  atr14?: (number | null)[];
  macd?: {
    macd: (number | null)[];
    signal: (number | null)[];
    histogram: (number | null)[];
  };
  bollinger?: {
    upper: (number | null)[];
    middle: (number | null)[];
    lower: (number | null)[];
  };
};

export type LiveChartApi = {
  applyLive: (candle: Candle) => void;
  scrollToRealtime: () => void;
};

type Props = {
  resetKey: string;
  candles: Candle[];
  /** Prefer imperative applyLive via onLiveApi for trade ticks (avoids React re-render). */
  liveCandle?: Candle | null;
  indicators?: IndicatorPack | null;
  indicatorsPreliminary?: boolean;
  enabled: Record<string, boolean>;
  markers: TradeMarker[];
  markerFilters: { sma: boolean; lab: boolean; shadow: boolean };
  positions: PositionOverlay[];
  liveFollow?: boolean;
  onUserScrollAway?: () => void;
  onNeedOlder?: () => void;
  onGoLiveReady?: (fn: () => void) => void;
  onLiveApi?: (api: LiveChartApi | null) => void;
};

function lineData(candles: Candle[], values: (number | null)[] | undefined) {
  if (!values) return [];
  const out: { time: UTCTimestamp; value: number }[] = [];
  for (let i = 0; i < candles.length; i++) {
    const v = values[i];
    if (v == null) continue;
    out.push({
      time: Math.floor(candles[i].open_time / 1000) as UTCTimestamp,
      value: v,
    });
  }
  return out;
}

function makeChart(el: HTMLElement, height: number) {
  return createChart(el, {
    autoSize: true,
    height,
    layout: {
      background: { type: ColorType.Solid, color: "#0e141d" },
      textColor: "#9eb0c7",
    },
    grid: {
      vertLines: { color: "#1a2433" },
      horzLines: { color: "#1a2433" },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#2a3a55" },
    timeScale: {
      borderColor: "#2a3a55",
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 8,
    },
  });
}

function markerAllowed(m: TradeMarker, f: Props["markerFilters"]) {
  const ledger = (m.ledger || m.source || "sma").toLowerCase();
  if (ledger.includes("lab")) return f.lab;
  if (
    ledger.includes("shadow") ||
    ledger.includes("prospect") ||
    ledger.includes("ml")
  )
    return f.shadow;
  if ((m.kind || "").toLowerCase() === "prediction") return f.shadow;
  return f.sma;
}

export default function CandleChart({
  resetKey,
  candles,
  liveCandle,
  indicators,
  indicatorsPreliminary,
  enabled,
  markers,
  markerFilters,
  positions,
  liveFollow = true,
  onUserScrollAway,
  onNeedOlder,
  onGoLiveReady,
  onLiveApi,
}: Props) {
  const mainRef = useRef<HTMLDivElement | null>(null);
  const rsiHost = useRef<HTMLDivElement | null>(null);
  const macdHost = useRef<HTMLDivElement | null>(null);
  const atrHost = useRef<HTMLDivElement | null>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const childChartsRef = useRef<IChartApi[]>([]);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlaySeriesRef = useRef<ISeriesApi<"Line">[]>([]);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const prevLenRef = useRef(0);
  const prevFirstRef = useRef<number | null>(null);
  const followRef = useRef(liveFollow);
  const loadLockRef = useRef(false);
  const candlesRef = useRef(candles);
  const markersRef = useRef(markers);
  const filtersRef = useRef(markerFilters);
  followRef.current = liveFollow;
  candlesRef.current = candles;
  markersRef.current = markers;
  filtersRef.current = markerFilters;

  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(
    null
  );
  const [markerTip, setMarkerTip] = useState<string | null>(null);

  // Create shell once per resetKey
  useEffect(() => {
    if (!mainRef.current) return;
    const chart = makeChart(mainRef.current, 480);
    chartRef.current = chart;
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderVisible: false,
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
      lastValueVisible: true,
      priceLineVisible: true,
    });
    candleSeriesRef.current = candleSeries;
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      lastValueVisible: false,
    });
    volumeSeriesRef.current = volumeSeries;
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });

    const goLive = () => chart.timeScale().scrollToRealTime();
    onGoLiveReady?.(goLive);
    const applyLive = (liveCandle: Candle) => {
      if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
      const t = Math.floor(liveCandle.open_time / 1000) as UTCTimestamp;
      candleSeriesRef.current.update({
        time: t,
        open: liveCandle.open,
        high: liveCandle.high,
        low: liveCandle.low,
        close: liveCandle.close,
      });
      volumeSeriesRef.current.update({
        time: t,
        value: liveCandle.volume,
        color:
          liveCandle.close >= liveCandle.open
            ? "rgba(38,166,154,0.4)"
            : "rgba(239,83,80,0.4)",
      });
      if (followRef.current) chart.timeScale().scrollToRealTime();
    };
    onLiveApi?.({ applyLive, scrollToRealtime: goLive });

    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range) return;
      if (followRef.current && range.to < candlesRef.current.length - 3) {
        onUserScrollAway?.();
      }
      if (range.from < 10 && !loadLockRef.current) {
        loadLockRef.current = true;
        onNeedOlder?.();
        window.setTimeout(() => {
          loadLockRef.current = false;
        }, 900);
      }
      for (const ch of childChartsRef.current) {
        try {
          ch.timeScale().setVisibleLogicalRange(range);
        } catch {
          /* panel may be empty */
        }
      }
    });

    chart.subscribeCrosshairMove((param: MouseEventParams) => {
      if (!param.time || !param.point || !candleSeriesRef.current) {
        setTip(null);
        return;
      }
      const data = param.seriesData.get(candleSeriesRef.current) as
        | { open: number; high: number; low: number; close: number }
        | undefined;
      const vol = volumeSeriesRef.current
        ? (param.seriesData.get(volumeSeriesRef.current) as
            | { value: number }
            | undefined)
        : undefined;
      if (!data) {
        setTip(null);
        return;
      }
      const t = Number(param.time);
      const filtered = markersRef.current.filter((m) =>
        markerAllowed(m, filtersRef.current)
      );
      const mk = filtered.find((m) => {
        const candle = candlesRef.current.find(
          (c) => Math.floor(c.open_time / 1000) === t
        );
        if (!candle) return false;
        return (
          candle.close_time === m.candle_ms ||
          candle.open_time === m.candle_ms ||
          (candle.open_time <= m.candle_ms &&
            (candle.close_time ?? candle.open_time + 60_000) >= m.candle_ms)
        );
      });
      setMarkerTip(
        mk
          ? [
              mk.label || mk.side,
              mk.kind === "prediction" ? "PREDICCIÓN (no ejecución)" : mk.ledger,
              mk.at,
              mk.price != null ? `px ${mk.price}` : null,
              mk.qty != null ? `qty ${mk.qty}` : null,
              mk.strategy,
              mk.reason,
            ]
              .filter(Boolean)
              .join(" · ")
          : null
      );
      setTip({
        x: param.point.x,
        y: param.point.y,
        text: `O ${data.open}  H ${data.high}  L ${data.low}  C ${data.close}${
          vol ? `  V ${vol.value}` : ""
        }`,
      });
    });

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: mainRef.current?.clientWidth });
    });
    ro.observe(mainRef.current);

    prevLenRef.current = 0;
    prevFirstRef.current = null;

    return () => {
      ro.disconnect();
      childChartsRef.current.forEach((c) => c.remove());
      childChartsRef.current = [];
      overlaySeriesRef.current = [];
      priceLinesRef.current = [];
      onLiveApi?.(null);
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      chartRef.current = null;
      chart.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  // Bars + scroll preservation on prepend
  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const chart = chartRef.current;
    if (!candleSeries || !volumeSeries || !chart || candles.length === 0) return;

    const prevLen = prevLenRef.current;
    const prevFirst = prevFirstRef.current;
    const range = chart.timeScale().getVisibleLogicalRange() as LogicalRange | null;
    const prepended =
      prevFirst != null && candles[0].open_time < prevFirst
        ? candles.length - prevLen
        : 0;

    candleSeries.setData(
      candles.map((c) => ({
        time: Math.floor(c.open_time / 1000) as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );
    volumeSeries.setData(
      candles.map((c) => ({
        time: Math.floor(c.open_time / 1000) as UTCTimestamp,
        value: c.volume,
        color:
          c.close >= c.open ? "rgba(38,166,154,0.4)" : "rgba(239,83,80,0.4)",
      }))
    );

    if (prevLen === 0) {
      chart.timeScale().fitContent();
    } else if (prepended > 0 && range) {
      chart.timeScale().setVisibleLogicalRange({
        from: range.from + prepended,
        to: range.to + prepended,
      });
    }

    prevLenRef.current = candles.length;
    prevFirstRef.current = candles[0].open_time;
  }, [candles, resetKey]);

  // Overlay indicators on main pane
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || candles.length === 0) return;
    for (const s of overlaySeriesRef.current) {
      try {
        chart.removeSeries(s);
      } catch {
        /* already gone */
      }
    }
    overlaySeriesRef.current = [];
    const add = (
      on: boolean,
      values: (number | null)[] | undefined,
      color: string
    ) => {
      if (!on || !values) return;
      const s = chart.addLineSeries({
        color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      s.setData(lineData(candles, values));
      overlaySeriesRef.current.push(s);
    };
    add(!!enabled.sma10, indicators?.sma10, "#e6c07b");
    add(!!enabled.sma20, indicators?.sma20, "#61afef");
    add(!!enabled.sma50, indicators?.sma50, "#c678dd");
    add(!!enabled.sma200, indicators?.sma200, "#98c379");
    add(!!enabled.ema9, indicators?.ema9, "#56b6c2");
    add(!!enabled.ema21, indicators?.ema21, "#d19a66");
    add(!!enabled.ema50, indicators?.ema50, "#be5046");
    if (enabled.bollinger && indicators?.bollinger) {
      add(true, indicators.bollinger.upper, "#5c6370");
      add(true, indicators.bollinger.middle, "#abb2bf");
      add(true, indicators.bollinger.lower, "#5c6370");
    }
  }, [candles, indicators, enabled, resetKey]);

  // Markers
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    const filtered = markers.filter((m) => markerAllowed(m, markerFilters));
    const markerData = filtered
      .map((m) => {
        const candle = candles.find(
          (c) =>
            c.close_time === m.candle_ms ||
            c.open_time === m.candle_ms ||
            (c.open_time <= m.candle_ms &&
              (c.close_time ?? c.open_time + 60_000) >= m.candle_ms)
        );
        const t = candle
          ? Math.floor(candle.open_time / 1000)
          : Math.floor(m.candle_ms / 1000);
        const pred =
          (m.kind || "").toLowerCase() === "prediction" ||
          (m.ledger || "").toLowerCase() === "shadow";
        const lab = (m.ledger || "").toLowerCase() === "lab";
        return {
          time: t as UTCTimestamp,
          position: m.side === "BUY" ? ("belowBar" as const) : ("aboveBar" as const),
          color: pred
            ? "#c678dd"
            : lab
              ? "#61afef"
              : m.side === "BUY"
                ? "#26a69a"
                : "#ef5350",
          shape: pred
            ? ("circle" as const)
            : m.side === "BUY"
              ? ("arrowUp" as const)
              : ("arrowDown" as const),
          text: m.label || (pred ? `PRED ${m.side}` : m.side),
        };
      })
      .sort((a, b) => Number(a.time) - Number(b.time));
    const byTime = new Map<number, (typeof markerData)[0]>();
    for (const mk of markerData) byTime.set(Number(mk.time), mk);
    series.setMarkers(
      Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time))
    );
  }, [markers, markerFilters, candles, resetKey]);

  // Position lines
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    for (const pl of priceLinesRef.current) {
      try {
        series.removePriceLine(pl);
      } catch {
        /* */
      }
    }
    priceLinesRef.current = [];
    for (const p of positions) {
      if (p.entry_price != null) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: p.entry_price,
            color: "#61afef",
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            axisLabelVisible: true,
            title: `${p.ledger.toUpperCase()} ENTRY`,
          })
        );
      }
      if (p.stop_loss_price != null) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: p.stop_loss_price,
            color: "#ef5350",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `${p.ledger.toUpperCase()} SL`,
          })
        );
      }
      if (p.take_profit_price != null) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: p.take_profit_price,
            color: "#98c379",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: `${p.ledger.toUpperCase()} TP`,
          })
        );
      }
      if (p.mark_price != null) {
        priceLinesRef.current.push(
          series.createPriceLine({
            price: p.mark_price,
            color: "#e6c07b",
            lineWidth: 1,
            lineStyle: LineStyle.SparseDotted,
            axisLabelVisible: true,
            title: "MARK",
          })
        );
      }
    }
  }, [positions, resetKey]);

  // Child panes RSI / MACD / ATR
  useEffect(() => {
    childChartsRef.current.forEach((c) => c.remove());
    childChartsRef.current = [];
    if (candles.length === 0) return;

    const makePane = (
      host: HTMLDivElement | null,
      on: boolean,
      height: number,
      paint: (ch: IChartApi) => void
    ) => {
      if (!host || !on) {
        if (host) host.innerHTML = "";
        return;
      }
      host.innerHTML = "";
      const ch = makeChart(host, height);
      paint(ch);
      childChartsRef.current.push(ch);
      const range = chartRef.current?.timeScale().getVisibleLogicalRange();
      if (range) ch.timeScale().setVisibleLogicalRange(range);
    };

    makePane(rsiHost.current, !!enabled.rsi && !!indicators?.rsi14, 120, (ch) => {
      ch.addLineSeries({ color: "#e6c07b", lineWidth: 2 }).setData(
        lineData(candles, indicators!.rsi14)
      );
    });
    makePane(macdHost.current, !!enabled.macd && !!indicators?.macd, 130, (ch) => {
      ch.addHistogramSeries({ priceScaleId: "hist" }).setData(
        lineData(candles, indicators!.macd!.histogram).map((d) => ({
          time: d.time,
          value: d.value,
          color: d.value >= 0 ? "rgba(38,166,154,0.45)" : "rgba(239,83,80,0.45)",
        }))
      );
      ch.addLineSeries({ color: "#61afef", lineWidth: 2 }).setData(
        lineData(candles, indicators!.macd!.macd)
      );
      ch.addLineSeries({ color: "#c678dd", lineWidth: 2 }).setData(
        lineData(candles, indicators!.macd!.signal)
      );
    });
    makePane(atrHost.current, !!enabled.atr && !!indicators?.atr14, 110, (ch) => {
      ch.addLineSeries({ color: "#d19a66", lineWidth: 2 }).setData(
        lineData(candles, indicators!.atr14)
      );
    });
  }, [candles, indicators, enabled.rsi, enabled.macd, enabled.atr, resetKey]);

  // Live incremental
  useEffect(() => {
    if (!liveCandle || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    const t = Math.floor(liveCandle.open_time / 1000) as UTCTimestamp;
    candleSeriesRef.current.update({
      time: t,
      open: liveCandle.open,
      high: liveCandle.high,
      low: liveCandle.low,
      close: liveCandle.close,
    });
    volumeSeriesRef.current.update({
      time: t,
      value: liveCandle.volume,
      color:
        liveCandle.close >= liveCandle.open
          ? "rgba(38,166,154,0.4)"
          : "rgba(239,83,80,0.4)",
    });
    if (followRef.current && chartRef.current) {
      chartRef.current.timeScale().scrollToRealTime();
    }
  }, [liveCandle]);

  return (
    <div style={{ position: "relative" }}>
      {tip && (
        <div
          style={{
            position: "absolute",
            left: Math.min(
              tip.x + 12,
              (mainRef.current?.clientWidth || 400) - 220
            ),
            top: Math.max(8, tip.y - 28),
            zIndex: 5,
            pointerEvents: "none",
            background: "rgba(14,20,29,0.92)",
            border: "1px solid #2a3a55",
            borderRadius: 4,
            padding: "4px 8px",
            fontSize: 11,
            color: "#d7e0ea",
            fontFamily: "ui-monospace, monospace",
          }}
        >
          {tip.text}
        </div>
      )}
      {markerTip && (
        <div className="pill info" style={{ marginBottom: 6 }}>
          {markerTip}
        </div>
      )}
      {indicatorsPreliminary && (
        <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>
          Indicadores de la última vela: preliminares (vela abierta).
        </div>
      )}
      <div ref={mainRef} style={{ width: "100%", height: 480 }} />
      {enabled.rsi && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            RSI14
          </div>
          <div ref={rsiHost} style={{ width: "100%", height: 120 }} />
        </div>
      )}
      {enabled.macd && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            MACD 12/26/9
          </div>
          <div ref={macdHost} style={{ width: "100%", height: 130 }} />
        </div>
      )}
      {enabled.atr && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            ATR14
          </div>
          <div ref={atrHost} style={{ width: "100%", height: 110 }} />
        </div>
      )}
    </div>
  );
}
