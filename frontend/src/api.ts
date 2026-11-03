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
  engine: Overview["engine"];
  last_scan: Scan | null;
  last_trade_at: string | null;
  prices_max_at: string | null;
  counts: Record<string, number>;
  binance_base: string;
  scan_limit: number;
  scan_every_seconds: number;
  audit: Array<{
    id: number;
    at: string;
    actor: string;
    action: string;
    detail: string | null;
  }>;
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
