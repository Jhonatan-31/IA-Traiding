export type Overview = {
  mode: string;
  initial_capital: number;
  cash: number;
  invested_cost: number;
  positions_market_value: number | null;
  equity_estimate: number | null;
  positions: number;
  trades: number;
  strategy: string;
  disclaimer: string;
  open_alerts?: number;
  latest: {
    id: number;
    at: string;
    markets: number;
    errors: number;
    equity: number | null;
  } | null;
  engine: {
    id: number;
    paused: boolean;
    updated_at: string;
    reason: string | null;
  } | null;
};

export type MlStatus = {
  state: string;
  runtime: {
    mode: string;
    active_model_version: string | null;
    notes: string | null;
  } | null;
  latest_model: {
    version: string;
    status: string;
    created_at: string;
    validated_for_research: boolean;
    mean_roc_auc_hist_gb: number | null;
    mean_roc_auc_naive: number | null;
    mean_ece_calibrated_test?: number | null;
    disclaimer: string | null;
  } | null;
  prediction_count: number;
  pending_resolution: number;
  resolved_count?: number;
  datasets: number;
  circuit_breaker?: {
    active: boolean;
    reason: string | null;
  } | null;
  execution_policy: string;
};

export type MlPrediction = {
  id: number;
  created_at: string;
  model_version: string;
  symbol: string;
  probability: number;
  proposed_action: string;
  accepted: boolean;
  reject_reason: string | null;
  observed_label: number | null;
  observed_net_return?: number | null;
  resolution_status?: string | null;
  source?: string | null;
  data_quality?: string | null;
};

export type Position = {
  symbol: string;
  qty: number;
  cost: number;
  price: number | null;
  price_source: string | null;
  price_at: string | null;
  market_value: number | null;
  unrealized_pnl: number | null;
};

export type Trade = {
  id: number;
  at: string;
  symbol: string;
  side: string;
  qty: number;
  price: number;
  candle_ms: number;
  fee_rate: number | null;
  slip_rate: number | null;
  strategy: string | null;
  reason: string | null;
};

export type Scan = {
  id: number;
  at: string;
  markets: number;
  errors: number;
  equity: number | null;
  cycle_ms?: number | null;
  last_candle_ms?: number | null;
};

export type Market = {
  symbol: string;
  price: number;
  source: string | null;
  at: string;
  has_position: boolean;
};

export type SystemInfo = {
  mode: string;
  checked_at?: string;
  engine: Overview["engine"];
  last_scan: Scan | null;
  last_trade_at: string | null;
  prices_max_at: string | null;
  counts: Record<string, number>;
  binance_base: string;
  binance?: BinanceDiag;
  scan_limit: number;
  scan_every_seconds: number;
  failed_requests_24h?: number;
  open_alerts?: number;
  components?: Record<
    string,
    { status: string; evidence?: unknown; latency_ms?: number }
  >;
  recent_errors?: Array<{
    id: number;
    at: string;
    level: string;
    message: string;
  }>;
  audit: Array<{
    id: number;
    at: string;
    actor: string;
    action: string;
    detail: string | null;
  }>;
  ohlcv_cache?: Record<string, number>;
  notes: string[];
};

export type Health = {
  status: string;
  mode: string;
  db: string;
  paused?: boolean;
  checked_at: string;
};

export type BinanceDiag = {
  status: string;
  latency_ms?: number;
  http_status?: number;
  error?: string;
  base: string;
  checked_at: string;
};

export type Candle = {
  open_time: number;
  close_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  is_closed: boolean;
};

export type ChartMarker = {
  id: number;
  at: string | null;
  side: string;
  qty: number | null;
  price: number | null;
  candle_ms: number;
  strategy: string | null;
  reason: string | null;
  ledger?: string;
  kind?: string;
  source?: string;
  label?: string;
};

export type ChartPositionOverlay = {
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

export type CandleResponse = {
  symbol: string;
  interval: string;
  fetched_at: string;
  count: number;
  closed_count: number;
  forming: Candle | null;
  candles: Candle[];
  cache: string;
  trade_markers: ChartMarker[];
  markers?: ChartMarker[];
  position_overlays?: ChartPositionOverlay[];
  history_cursor?: {
    oldest_open_ms: number | null;
    newest_open_ms: number | null;
    end_time_requested: number | null;
    has_more: boolean;
  };
  indicators?: {
    sma10: (number | null)[];
    sma20: (number | null)[];
    sma50: (number | null)[];
    sma200: (number | null)[];
    ema9: (number | null)[];
    ema21: (number | null)[];
    ema50: (number | null)[];
    rsi14: (number | null)[];
    atr14: (number | null)[];
    macd: {
      macd: (number | null)[];
      signal: (number | null)[];
      histogram: (number | null)[];
    };
    bollinger: {
      upper: (number | null)[];
      middle: (number | null)[];
      lower: (number | null)[];
    };
  };
  indicators_meta?: {
    last_bar_preliminary: boolean;
    note?: string;
  };
};

export type RiskReport = {
  cash: number;
  invested_cost: number;
  positions_market_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  fees_estimated: number;
  equity_estimate: number | null;
  open_positions: number;
  total_exposure_pct_of_initial: number | null;
  drawdown: {
    current_drawdown_pct: number | null;
    max_drawdown_pct: number | null;
    peak_equity: number | null;
    points: number;
  };
  daily_pnl_pct_vs_first_scan: number | null;
  exposure_by_asset: Array<{
    symbol: string;
    cost: number;
    market_value: number | null;
    unrealized_pnl: number | null;
    valuation: string;
    price_source?: string | null;
  }>;
  limits: Record<string, number>;
  breaches: string[];
  classification: Record<string, string>;
  disclaimer: string;
};

export type AlertRow = {
  id: number;
  created_at: string;
  updated_at: string;
  severity: string;
  code: string;
  title: string;
  detail: string | null;
  status: string;
  fingerprint: string;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${path} → HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  overview: () => getJson<Overview>("/api/overview"),
  positions: () => getJson<Position[]>("/api/positions"),
  trades: (limit = 100) => getJson<Trade[]>(`/api/trades?limit=${limit}`),
  scans: () => getJson<Scan[]>("/api/scans"),
  markets: () => getJson<Market[]>("/api/markets"),
  system: () => getJson<SystemInfo>("/api/system"),
  health: () => getJson<Health>("/api/health"),
  binance: () => getJson<BinanceDiag>("/api/diagnostics/binance"),
  pause: async (reason = "dashboard_pause") => {
    const res = await fetch(`/api/engine/pause?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(`pause → HTTP ${res.status}`);
    return res.json();
  },
  resume: async (reason = "dashboard_resume") => {
    const res = await fetch(`/api/engine/resume?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(`resume → HTTP ${res.status}`);
    return res.json();
  },
  candles: (
    symbol: string,
    interval: string,
    limit = 300,
    indicators = true,
    endTime?: number
  ) => {
    const q = new URLSearchParams({
      symbol,
      interval,
      limit: String(limit),
      indicators: String(indicators),
    });
    if (endTime != null) q.set("end_time", String(endTime));
    return getJson<CandleResponse>(`/api/candles?${q}`);
  },
  risk: () => getJson<RiskReport>("/api/risk"),
  alerts: (status?: string) =>
    getJson<AlertRow[]>(
      status ? `/api/alerts?status=${encodeURIComponent(status)}` : "/api/alerts"
    ),
  evaluateAlerts: async () => {
    const res = await fetch("/api/alerts/evaluate", { method: "POST" });
    if (!res.ok) throw new Error(`alerts/evaluate → HTTP ${res.status}`);
    return res.json();
  },
  ackAlert: async (id: number) => {
    const res = await fetch(`/api/alerts/${id}/ack`, { method: "POST" });
    if (!res.ok) throw new Error(`ack → HTTP ${res.status}`);
    return res.json();
  },
  mlStatus: () => getJson<MlStatus>("/api/ml/status"),
  mlPredictions: (limit = 50, opts?: { unresolved?: boolean; resolvedOnly?: boolean }) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (opts?.unresolved) q.set("unresolved", "true");
    if (opts?.resolvedOnly) q.set("resolved_only", "true");
    return getJson<MlPrediction[]>(`/api/ml/predictions?${q}`);
  },
  mlPredictionsSummary: () =>
    getJson<Record<string, unknown>>("/api/ml/predictions/summary"),
  mlComparison: () => getJson<Record<string, unknown>>("/api/ml/comparison"),
  mlResearchLatest: () => getJson<Record<string, unknown>>("/api/ml/research/latest"),
  mlMetricsAudit: () => getJson<Record<string, unknown>>("/api/ml/metrics-audit"),
  mlCircuitBreaker: () => getJson<Record<string, unknown>>("/api/ml/circuit-breaker"),
  mlCircuitEvaluate: async () => {
    const res = await fetch("/api/ml/circuit-breaker/evaluate", { method: "POST" });
    if (!res.ok) throw new Error(`circuit-breaker → HTTP ${res.status}`);
    return res.json();
  },
  mlResolve: async () => {
    const res = await fetch("/api/ml/resolve", { method: "POST" });
    if (!res.ok) throw new Error(`resolve → HTTP ${res.status}`);
    return res.json() as Promise<{ resolved: number; still_pending: number }>;
  },
  mlShadowReplay: async (max_per_symbol = 6) => {
    const res = await fetch(
      `/api/ml/shadow/replay?max_per_symbol=${max_per_symbol}`,
      { method: "POST" }
    );
    if (!res.ok) throw new Error(`shadow/replay → HTTP ${res.status}`);
    return res.json() as Promise<{ attempted: number; inserted_delta: number }>;
  },
  mlShadowRun: async (limit_symbols = 10) => {
    const res = await fetch(`/api/ml/shadow/run?limit_symbols=${limit_symbols}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(`shadow/run → HTTP ${res.status}`);
    return res.json() as Promise<{ generated: number; items: unknown[] }>;
  },
  prospectStatus: () => getJson<Record<string, unknown>>("/api/prospect/status"),
  prospectDecisions: (
    limit = 50,
    opts?: {
      experiment_type?: string;
      strategy?: string;
      symbol?: string;
      status?: string;
    }
  ) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (opts?.experiment_type) q.set("experiment_type", opts.experiment_type);
    if (opts?.strategy) q.set("strategy", opts.strategy);
    if (opts?.symbol) q.set("symbol", opts.symbol);
    if (opts?.status) q.set("status", opts.status);
    return getJson<Record<string, unknown>[]>(`/api/prospect/decisions?${q}`);
  },
  prospectBenchmarks: () =>
    getJson<Record<string, unknown>>("/api/prospect/benchmarks"),
  prospectScheduler: () =>
    getJson<Record<string, unknown>>("/api/prospect/scheduler"),
  prospectMetrics: (experiment_type = "SHADOW_LIVE") =>
    getJson<Record<string, unknown>>(
      `/api/prospect/metrics?experiment_type=${encodeURIComponent(experiment_type)}`
    ),
  prospectAlerts: (status = "OPEN") =>
    getJson<Record<string, unknown>[]>(
      `/api/prospect/alerts?status=${encodeURIComponent(status)}`
    ),
  prospectAlertsEvaluate: async () => {
    const res = await fetch("/api/prospect/alerts/evaluate", { method: "POST" });
    if (!res.ok) throw new Error(`prospect alerts → HTTP ${res.status}`);
    return res.json() as Promise<Record<string, unknown>>;
  },
  prospectAudit: () => getJson<Record<string, unknown>>("/api/prospect/audit"),
  prospectReport: (experiment_type = "SHADOW_LIVE") =>
    getJson<Record<string, unknown>>(
      `/api/prospect/report?experiment_type=${encodeURIComponent(experiment_type)}`
    ),
  prospectHorizons: () => getJson<Record<string, unknown>>("/api/prospect/horizons"),
  prospectReconcile: async () => {
    const res = await fetch("/api/prospect/reconcile", { method: "POST" });
    if (!res.ok) throw new Error(`prospect reconcile → HTTP ${res.status}`);
    return res.json() as Promise<Record<string, unknown>>;
  },
  prospectShadowLiveRun: async () => {
    const res = await fetch("/api/prospect/shadow-live/run", { method: "POST" });
    if (!res.ok) throw new Error(`prospect shadow-live → HTTP ${res.status}`);
    return res.json() as Promise<{ generated: number; items: unknown[] }>;
  },
  prospectResolve: async () => {
    const res = await fetch("/api/prospect/resolve", { method: "POST" });
    if (!res.ok) throw new Error(`prospect resolve → HTTP ${res.status}`);
    return res.json() as Promise<{
      resolved: number;
      invalid: number;
      still_pending: number;
    }>;
  },
  performanceCompare: () =>
    getJson<Record<string, unknown>>("/api/performance/compare"),
  expressStatus: () => getJson<Record<string, unknown>>("/api/express/status"),
  expressReport: () => getJson<Record<string, unknown>>("/api/express/report"),
  demoStatus: () => getJson<Record<string, unknown>>("/api/demo/status"),
  demoStart: async (token: string) => {
    const res = await fetch("/api/demo/start", {
      method: "POST",
      headers: { "X-Lab-Token": token },
    });
    if (!res.ok) throw new Error(`demo start → HTTP ${res.status}`);
    return res.json() as Promise<Record<string, unknown>>;
  },
  demoStop: async (token: string) => {
    const res = await fetch("/api/demo/stop", {
      method: "POST",
      headers: { "X-Lab-Token": token },
    });
    if (!res.ok) throw new Error(`demo stop → HTTP ${res.status}`);
    return res.json() as Promise<Record<string, unknown>>;
  },
  demoDecisions: (limit = 100, symbol?: string, action?: string) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (symbol) q.set("symbol", symbol);
    if (action) q.set("action", action);
    return getJson<Array<Record<string, unknown>>>(`/api/demo/decisions?${q}`);
  },
  demoFills: (limit = 100, symbol?: string) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (symbol) q.set("symbol", symbol);
    return getJson<Array<Record<string, unknown>>>(`/api/demo/fills?${q}`);
  },
  demoMarkers: (symbol: string) =>
    getJson<{ markers: Array<Record<string, unknown>>; ledger: string }>(
      `/api/demo/markers?symbol=${encodeURIComponent(symbol)}`
    ),
  labStatus: () => getJson<Record<string, unknown>>("/api/lab/status"),
  labPause: async (token: string, reason = "dashboard_pause") => {
    const res = await fetch(`/api/lab/pause?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
      headers: { "X-Lab-Token": token },
    });
    if (!res.ok) throw new Error(`lab pause → HTTP ${res.status}`);
    return res.json();
  },
  labResume: async (token: string, reason = "dashboard_resume") => {
    const res = await fetch(`/api/lab/resume?reason=${encodeURIComponent(reason)}`, {
      method: "POST",
      headers: { "X-Lab-Token": token },
    });
    if (!res.ok) throw new Error(`lab resume → HTTP ${res.status}`);
    return res.json();
  },
  labCycle: async (token: string) => {
    const res = await fetch("/api/lab/cycle", {
      method: "POST",
      headers: { "X-Lab-Token": token },
    });
    if (!res.ok) throw new Error(`lab cycle → HTTP ${res.status}`);
    return res.json() as Promise<Record<string, unknown>>;
  },
};

export function fmtNum(n: number | null | undefined, digits = 4): string {
  if (n == null || Number.isNaN(n)) return "Sin datos";
  return n.toLocaleString("es-CO", { maximumFractionDigits: digits });
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "Sin datos";
  return `${n.toFixed(2)}%`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "Sin datos";
  return new Date(iso).toLocaleString("es-CO");
}
