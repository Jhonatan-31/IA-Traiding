/** Pure helpers for chart candle merge / live guards (no React). */

export type CandleBar = {
  open_time: number;
  close_time?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_closed?: boolean;
};

export type LiveKline = {
  candle_open_ms: number;
  event_time_ms?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_closed: boolean;
};

/** Keep chronological unique open_time ascending. */
export function mergeCandles(
  existing: CandleBar[],
  incoming: CandleBar[],
  mode: "prepend" | "replace" | "append" = "prepend"
): CandleBar[] {
  const map = new Map<number, CandleBar>();
  const base = mode === "replace" ? [] : existing;
  for (const c of base) map.set(c.open_time, c);
  for (const c of incoming) map.set(c.open_time, c);
  // prepend/append share dedupe+sort; difference is only caller intent
  return Array.from(map.values()).sort((a, b) => a.open_time - b.open_time);
}

export function shouldApplyLive(
  lastOpenMs: number | null,
  lastEventMs: number | null,
  msg: LiveKline
): boolean {
  const openMs = msg.candle_open_ms;
  const eventMs = msg.event_time_ms ?? openMs;
  if (lastOpenMs != null && openMs < lastOpenMs) return false;
  if (
    lastOpenMs === openMs &&
    lastEventMs != null &&
    eventMs < lastEventMs
  ) {
    return false;
  }
  return true;
}

export function applyLiveCandle(
  candles: CandleBar[],
  live: LiveKline
): CandleBar[] {
  const bar: CandleBar = {
    open_time: live.candle_open_ms,
    open: live.open,
    high: live.high,
    low: live.low,
    close: live.close,
    volume: live.volume,
    is_closed: live.is_closed,
  };
  if (!candles.length) return [bar];
  const last = candles[candles.length - 1];
  if (last.open_time === bar.open_time) {
    return [...candles.slice(0, -1), bar];
  }
  if (bar.open_time > last.open_time) {
    return [...candles, bar];
  }
  return candles;
}

export function detectGapMs(
  older: CandleBar[],
  newer: CandleBar[],
  intervalMs: number
): number | null {
  if (!older.length || !newer.length) return null;
  const a = older[older.length - 1].open_time;
  const b = newer[0].open_time;
  const gap = b - a;
  if (gap > intervalMs * 1.5) return gap;
  return null;
}

export const INTERVAL_MS: Record<string, number> = {
  "1m": 60_000,
  "5m": 300_000,
  "15m": 900_000,
  "1h": 3_600_000,
  "4h": 14_400_000,
  "1d": 86_400_000,
};
