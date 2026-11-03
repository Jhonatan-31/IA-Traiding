"""Trade → forming candle aggregation (visualization only; not for SMA/Shadow signals)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}

# Bounded dedupe window per forming candle
_MAX_SEEN_IDS = 4_096


def candle_open_ms(trade_time_ms: int, interval: str) -> int:
    step = INTERVAL_MS[interval]
    return (int(trade_time_ms) // step) * step


@dataclass
class FormingCandle:
    symbol: str
    interval: str
    candle_open_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    event_time_ms: int
    last_trade_id: int | None = None
    last_trade_time_ms: int | None = None
    trade_count: int = 0
    is_closed: bool = False
    source: str = "trade"
    seen_ids: set[int] = field(default_factory=set)
    volume_mode: str = "trade_sum"  # trade_sum | kline_abs

    def to_msg(self, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        out = {
            "type": "candle_tick",
            "symbol": self.symbol,
            "interval": self.interval,
            "candle_open_ms": self.candle_open_ms,
            "event_time_ms": self.event_time_ms,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_closed": self.is_closed,
            "source": self.source,
            "last_trade_id": self.last_trade_id,
            "last_trade_time_ms": self.last_trade_time_ms,
            "trade_count": self.trade_count,
            "volume_mode": self.volume_mode,
        }
        if extra:
            out.update(extra)
        return out


class CandleAggregator:
    """Per symbol+interval forming candle driven by trades, reconciled by klines."""

    def __init__(self) -> None:
        self._candles: dict[str, FormingCandle] = {}

    @staticmethod
    def key(symbol: str, interval: str) -> str:
        return f"{symbol}:{interval}"

    def get(self, symbol: str, interval: str) -> FormingCandle | None:
        return self._candles.get(self.key(symbol, interval))

    def apply_trade(self, trade: dict[str, Any], interval: str) -> FormingCandle | None:
        """
        Apply a public trade. Returns updated candle or None if rejected
        (duplicate id, stale time, closed candle overwrite, etc.).
        """
        symbol = trade["symbol"]
        trade_id = int(trade["trade_id"])
        price = float(trade["price"])
        qty = float(trade["qty"])
        trade_time = int(trade["trade_time_ms"])
        event_time = int(trade["event_time_ms"])
        open_ms = candle_open_ms(trade_time, interval)
        k = self.key(symbol, interval)
        cur = self._candles.get(k)

        if cur is not None:
            if open_ms < cur.candle_open_ms:
                return None  # late trade for older bar
            if open_ms == cur.candle_open_ms and cur.is_closed:
                return None  # do not mutate confirmed bar via trade
            if trade_id in cur.seen_ids:
                return None
            if cur.last_trade_id is not None and trade_id < cur.last_trade_id:
                # out-of-order older id on same/new bar — skip for volume safety
                if open_ms == cur.candle_open_ms:
                    return None

        if cur is None or open_ms > cur.candle_open_ms:
            cur = FormingCandle(
                symbol=symbol,
                interval=interval,
                candle_open_ms=open_ms,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=qty,
                event_time_ms=event_time,
                last_trade_id=trade_id,
                last_trade_time_ms=trade_time,
                trade_count=1,
                is_closed=False,
                source="trade",
                seen_ids={trade_id},
                volume_mode="trade_sum",
            )
            self._candles[k] = cur
            return cur

        # same forming candle
        cur.high = max(cur.high, price)
        cur.low = min(cur.low, price)
        cur.close = price
        if cur.volume_mode == "trade_sum":
            cur.volume += qty
        # if volume was reconciled from kline absolute, keep kline vol until next kline;
        # still update OHLC from trade for responsiveness
        cur.event_time_ms = max(cur.event_time_ms, event_time)
        cur.last_trade_id = trade_id
        cur.last_trade_time_ms = trade_time
        cur.trade_count += 1
        cur.source = "trade"
        cur.seen_ids.add(trade_id)
        if len(cur.seen_ids) > _MAX_SEEN_IDS:
            # drop arbitrary half by rebuild (ids are roughly sequential)
            cur.seen_ids = set(sorted(cur.seen_ids)[-_MAX_SEEN_IDS // 2 :])
        return cur

    def apply_kline(self, kline: dict[str, Any]) -> FormingCandle | None:
        """Reconcile with official kline; kline is authoritative for closed bars."""
        symbol = kline["symbol"]
        interval = kline["interval"]
        open_ms = int(kline["candle_open_ms"])
        event_ms = int(kline["event_time_ms"])
        k = self.key(symbol, interval)
        cur = self._candles.get(k)
        is_closed = bool(kline.get("is_closed"))

        if cur is not None and open_ms < cur.candle_open_ms:
            return None
        if cur is not None and open_ms == cur.candle_open_ms and event_ms < cur.event_time_ms and not is_closed:
            # stale open kline behind newer trade-driven state — still allow volume reconcile
            if float(kline["volume"]) >= cur.volume:
                cur.volume = float(kline["volume"])
                cur.volume_mode = "kline_abs"
            return None

        if cur is None or open_ms > (cur.candle_open_ms if cur else -1):
            cur = FormingCandle(
                symbol=symbol,
                interval=interval,
                candle_open_ms=open_ms,
                open=float(kline["open"]),
                high=float(kline["high"]),
                low=float(kline["low"]),
                close=float(kline["close"]),
                volume=float(kline["volume"]),
                event_time_ms=event_ms,
                is_closed=is_closed,
                source="kline",
                volume_mode="kline_abs",
                trade_count=0,
            )
            self._candles[k] = cur
            return cur

        # same open: merge — never lower high/raise low incorrectly; prefer wider range
        cur.high = max(cur.high, float(kline["high"]))
        cur.low = min(cur.low, float(kline["low"]))
        # close: kline close if closed or if kline event newer
        if is_closed or event_ms >= cur.event_time_ms:
            cur.close = float(kline["close"])
            if cur.open == 0:
                cur.open = float(kline["open"])
            # Prefer official open from kline when starting from trades mid-bar is wrong
            # Only set open from kline if we never had a trade open (trade_count==0) or closed
            if cur.trade_count == 0 or is_closed:
                cur.open = float(kline["open"])
                cur.high = float(kline["high"])
                cur.low = float(kline["low"])
                cur.close = float(kline["close"])
        cur.volume = float(kline["volume"])
        cur.volume_mode = "kline_abs"
        cur.event_time_ms = max(cur.event_time_ms, event_ms)
        cur.is_closed = is_closed
        cur.source = "kline" if is_closed else cur.source
        if is_closed:
            cur.source = "kline"
            cur.seen_ids.clear()
        return cur
