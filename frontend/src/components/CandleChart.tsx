import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

export type Candle = {
  open_time: number;
  close_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_closed: boolean;
};

export type TradeMarker = {
  id: number;
  side: string;
  price: number;
  candle_ms: number;
  at: string;
};

export type IndicatorPack = {
  sma10?: (number | null)[];
  sma20?: (number | null)[];
  sma50?: (number | null)[];
  sma200?: (number | null)[];
  ema9?: (number | null)[];
  ema21?: (number | null)[];
  ema50?: (number | null)[];
  bollinger?: {
    upper: (number | null)[];
    middle: (number | null)[];
    lower: (number | null)[];
  };
};

type Props = {
  candles: Candle[];
  indicators?: IndicatorPack | null;
  enabled: Record<string, boolean>;
  markers: TradeMarker[];
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

export default function CandleChart({
  candles,
  indicators,
  enabled,
  markers,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#121a2b" },
        textColor: "#8fa3bb",
      },
      grid: {
        vertLines: { color: "#1c2940" },
        horzLines: { color: "#1c2940" },
      },
      rightPriceScale: { borderColor: "#2a3a55" },
      timeScale: { borderColor: "#2a3a55", timeVisible: true },
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#2dd4bf",
      downColor: "#f07178",
      borderVisible: false,
      wickUpColor: "#2dd4bf",
      wickDownColor: "#f07178",
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
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
        color: c.close >= c.open ? "rgba(45,212,191,0.35)" : "rgba(240,113,120,0.35)",
      }))
    );

    const lines: ISeriesApi<"Line">[] = [];
    const addLine = (
      key: string,
      values: (number | null)[] | undefined,
      color: string
    ) => {
      if (!enabled[key] || !values) return;
      const s = chart.addLineSeries({ color, lineWidth: 2, priceLineVisible: false });
      s.setData(lineData(candles, values));
      lines.push(s);
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
          (c) => c.close_time === m.candle_ms || c.open_time <= m.candle_ms && c.close_time >= m.candle_ms
        );
        const t = candle
          ? Math.floor(candle.open_time / 1000)
          : Math.floor(m.candle_ms / 1000);
        return {
          time: t as UTCTimestamp,
          position: m.side === "BUY" ? ("belowBar" as const) : ("aboveBar" as const),
          color: m.side === "BUY" ? "#2dd4bf" : "#f07178",
          shape: m.side === "BUY" ? ("arrowUp" as const) : ("arrowDown" as const),
          text: m.side,
        };
      })
      .sort((a, b) => Number(a.time) - Number(b.time));
    if (markerData.length) candleSeries.setMarkers(markerData);

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, indicators, enabled, markers]);

  return <div ref={ref} style={{ width: "100%", height: 460 }} />;
}
