import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
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
  price: number;
  candle_ms: number;
  at: string;
  source?: string;
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

type Props = {
  candles: Candle[];
  liveCandle?: Candle | null;
  indicators?: IndicatorPack | null;
  enabled: Record<string, boolean>;
  markers: TradeMarker[];
  liveFollow?: boolean;
  onUserScrollAway?: () => void;
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
      secondsVisible: true,
    },
  });
}

export default function CandleChart({
  candles,
  liveCandle,
  indicators,
  enabled,
  markers,
  liveFollow = true,
  onUserScrollAway,
}: Props) {
  const mainRef = useRef<HTMLDivElement | null>(null);
  const rsiRef = useRef<HTMLDivElement | null>(null);
  const macdRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const followRef = useRef(liveFollow);
  followRef.current = liveFollow;

  // Mount chart once per candles baseline / indicator toggle (not every live tick)
  useEffect(() => {
    if (!mainRef.current || candles.length === 0) return;
    const charts: IChartApi[] = [];
    const chart = makeChart(mainRef.current, 460);
    charts.push(chart);
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
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

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

    const addLine = (
      key: string,
      values: (number | null)[] | undefined,
      color: string
    ) => {
      if (!enabled[key] || !values) return;
      const s = chart.addLineSeries({
        color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      s.setData(lineData(candles, values));
    };

    addLine("sma10", indicators?.sma10, "#e6c07b");
    addLine("sma20", indicators?.sma20, "#61afef");
    addLine("sma50", indicators?.sma50, "#c678dd");
    addLine("sma200", indicators?.sma200, "#98c379");
    addLine("ema9", indicators?.ema9, "#56b6c2");
    addLine("ema21", indicators?.ema21, "#d19a66");
    addLine("ema50", indicators?.ema50, "#be5046");
    if (enabled.bollinger && indicators?.bollinger) {
      addLine("bb_upper", indicators.bollinger.upper, "#5c6370");
      addLine("bb_mid", indicators.bollinger.middle, "#5c6370");
      addLine("bb_lower", indicators.bollinger.lower, "#5c6370");
    }

    const markerData = markers
      .map((m) => {
        const candle = candles.find(
          (c) =>
            c.close_time === m.candle_ms ||
            (c.open_time <= m.candle_ms &&
              (c.close_time ?? c.open_time + 60_000) >= m.candle_ms)
        );
        const t = candle
          ? Math.floor(candle.open_time / 1000)
          : Math.floor(m.candle_ms / 1000);
        const shadow = (m.source || "").toLowerCase().includes("shadow");
        return {
          time: t as UTCTimestamp,
          position: m.side === "BUY" ? ("belowBar" as const) : ("aboveBar" as const),
          color: shadow
            ? "#c678dd"
            : m.side === "BUY"
              ? "#26a69a"
              : "#ef5350",
          shape: m.side === "BUY" ? ("arrowUp" as const) : ("arrowDown" as const),
          text: shadow ? `SH ${m.side}` : m.side,
        };
      })
      .sort((a, b) => Number(a.time) - Number(b.time));
    if (markerData.length) candleSeries.setMarkers(markerData);

    chart.timeScale().fitContent();

    const onRange = () => {
      if (!followRef.current) return;
      // if user dragged away while follow was on, notify parent once via logical check
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
      onRange();
      if (!followRef.current && onUserScrollAway) onUserScrollAway();
    });

    if (rsiRef.current && enabled.rsi && indicators?.rsi14) {
      const rsiChart = makeChart(rsiRef.current, 130);
      charts.push(rsiChart);
      const s = rsiChart.addLineSeries({ color: "#e6c07b", lineWidth: 2 });
      s.setData(lineData(candles, indicators.rsi14));
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
      });
    }

    if (macdRef.current && enabled.macd && indicators?.macd) {
      const macdChart = makeChart(macdRef.current, 140);
      charts.push(macdChart);
      const hist = macdChart.addHistogramSeries({ priceScaleId: "hist" });
      hist.setData(
        lineData(candles, indicators.macd.histogram).map((d) => ({
          time: d.time,
          value: d.value,
          color: d.value >= 0 ? "rgba(38,166,154,0.45)" : "rgba(239,83,80,0.45)",
        }))
      );
      macdChart
        .addLineSeries({ color: "#61afef", lineWidth: 2 })
        .setData(lineData(candles, indicators.macd.macd));
      macdChart
        .addLineSeries({ color: "#c678dd", lineWidth: 2 })
        .setData(lineData(candles, indicators.macd.signal));
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) macdChart.timeScale().setVisibleLogicalRange(range);
      });
    }

    const ro = new ResizeObserver(() => {
      // autoSize handles most; force apply width
      chart.applyOptions({ width: mainRef.current?.clientWidth });
    });
    if (mainRef.current) ro.observe(mainRef.current);

    return () => {
      ro.disconnect();
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      chartRef.current = null;
      charts.forEach((c) => c.remove());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- live ticks must not remount
  }, [candles, indicators, enabled, markers]);

  // Incremental live candle update (no setData rebuild)
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
    <div>
      <div ref={mainRef} style={{ width: "100%", height: 460 }} />
      {enabled.rsi && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            RSI14
          </div>
          <div ref={rsiRef} style={{ width: "100%", height: 130 }} />
        </div>
      )}
      {enabled.macd && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            MACD
          </div>
          <div ref={macdRef} style={{ width: "100%", height: 140 }} />
        </div>
      )}
    </div>
  );
}

/** Expose scroll helper for parent buttons */
export function scrollChartToRealtime(chartHost?: HTMLElement | null) {
  void chartHost;
}
