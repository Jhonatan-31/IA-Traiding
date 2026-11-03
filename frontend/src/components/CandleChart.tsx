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
  rsi14?: (number | null)[];
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

function makeChart(el: HTMLElement, height: number) {
  return createChart(el, {
    autoSize: true,
    height,
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
}

export default function CandleChart({
  candles,
  indicators,
  enabled,
  markers,
}: Props) {
  const mainRef = useRef<HTMLDivElement | null>(null);
  const rsiRef = useRef<HTMLDivElement | null>(null);
  const macdRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!mainRef.current) return;
    const charts: IChartApi[] = [];
    const chart = makeChart(mainRef.current, 420);
    charts.push(chart);

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
          (c) =>
            c.close_time === m.candle_ms ||
            (c.open_time <= m.candle_ms && c.close_time >= m.candle_ms)
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

    if (rsiRef.current && enabled.rsi && indicators?.rsi14) {
      const rsiChart = makeChart(rsiRef.current, 140);
      charts.push(rsiChart);
      const s = rsiChart.addLineSeries({ color: "#e6c07b", lineWidth: 2 });
      s.setData(lineData(candles, indicators.rsi14));
      rsiChart.timeScale().fitContent();
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
      });
    }

    if (macdRef.current && enabled.macd && indicators?.macd) {
      const macdChart = makeChart(macdRef.current, 150);
      charts.push(macdChart);
      const hist = macdChart.addHistogramSeries({ priceScaleId: "hist" });
      hist.setData(
        lineData(candles, indicators.macd.histogram).map((d) => ({
          time: d.time,
          value: d.value,
          color: d.value >= 0 ? "rgba(45,212,191,0.5)" : "rgba(240,113,120,0.5)",
        }))
      );
      const macdLine = macdChart.addLineSeries({ color: "#61afef", lineWidth: 2 });
      macdLine.setData(lineData(candles, indicators.macd.macd));
      const sig = macdChart.addLineSeries({ color: "#c678dd", lineWidth: 2 });
      sig.setData(lineData(candles, indicators.macd.signal));
      macdChart.timeScale().fitContent();
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (range) macdChart.timeScale().setVisibleLogicalRange(range);
      });
    }

    return () => {
      charts.forEach((c) => c.remove());
    };
  }, [candles, indicators, enabled, markers]);

  return (
    <div>
      <div ref={mainRef} style={{ width: "100%", height: 420 }} />
      {enabled.rsi && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            RSI14
          </div>
          <div ref={rsiRef} style={{ width: "100%", height: 140 }} />
        </div>
      )}
      {enabled.macd && (
        <div style={{ marginTop: 8 }}>
          <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            MACD
          </div>
          <div ref={macdRef} style={{ width: "100%", height: 150 }} />
        </div>
      )}
    </div>
  );
}
