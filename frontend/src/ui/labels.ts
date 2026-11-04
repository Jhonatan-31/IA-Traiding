/** Capa de presentación — backend conserva nombres técnicos; UI habla humano. */

export const ACCOUNT_LABEL: Record<string, string> = {
  demo_manual_control: "Bot Demo",
  lab_auto: "Bot Automático",
  research_sim: "Investigación IA",
  express_test_20261103: "Prueba Express",
  sma_paper: "Cuenta papel (SMA)",
  "1": "Cuenta papel (SMA)",
};

export const ACTION_LABEL: Record<string, string> = {
  BUY: "Comprar",
  SELL: "Vender",
  HOLD: "Esperar",
};

export const STATUS_LABEL: Record<string, string> = {
  RUNNING: "En marcha",
  STOPPED: "Detenido",
  FILLED: "Operación ejecutada",
  SIGNAL_ONLY: "Señal detectada",
  PENDING: "Pendiente de evaluación",
  RESOLVED: "Evaluación completada",
  INVALID: "No evaluable",
  REJECTED: "No se ejecutó",
  CANCELLED: "Cancelada",
  NEW: "En cola",
  VALIDATED: "Validada",
  OK: "Correcto",
  ERROR: "Con problemas",
  WARNING: "Atención",
};

export const REASON_HINT: Record<string, string> = {
  bot_stopped_entries_blocked: "El bot está detenido: no abre compras nuevas.",
  flags_2_of_5_insufficient: "La señal no fue lo bastante clara (2 de 5 condiciones).",
  flags_3_of_5_insufficient: "La señal no fue lo bastante clara (3 de 5 condiciones).",
  flags_1_of_5_insufficient: "La señal fue débil (1 de 5 condiciones).",
  flags_0_of_5_insufficient: "Sin condiciones favorables en este momento.",
  no_clear_signal: "Sin oportunidad clara en este ciclo.",
  trend_not_aligned: "La tendencia aún no confirma una compra.",
  peak_drawdown_pause: "Pausa por protección: la cuenta bajó desde su máximo.",
  max_positions: "Ya hay el máximo de posiciones abiertas.",
  max_exposure: "Se alcanzó el límite de dinero invertido.",
  stop_loss_1pct: "Venta por protección de pérdida (−1%).",
  take_profit_2pct: "Venta por objetivo de ganancia (+2%).",
  trend_break_1m: "Venta: la tendencia a corto plazo se debilitó.",
  demo_policy_buy: "Compra virtual según las reglas del Bot Demo.",
  stop_loss: "Venta por protección de pérdida.",
  take_profit: "Venta por objetivo de ganancia.",
};

export function accountLabel(id: string | null | undefined): string {
  if (!id) return "Cuenta";
  return ACCOUNT_LABEL[id] || "Cuenta virtual";
}

export function actionLabel(a: string | null | undefined): string {
  if (!a) return "—";
  return ACTION_LABEL[a.toUpperCase()] || a;
}

export function statusLabel(s: string | null | undefined): string {
  if (!s) return "—";
  return STATUS_LABEL[s.toUpperCase()] || s;
}

export function reasonLabel(r: string | null | undefined): string {
  if (!r) return "Sin detalle";
  if (REASON_HINT[r]) return REASON_HINT[r];
  if (r.startsWith("flags_") && r.includes("_of_5")) {
    const m = r.match(/flags_(\d)_of_5/);
    if (m) return `La señal no fue lo bastante clara (${m[1]} de 5 condiciones).`;
  }
  if (r.startsWith("policy_") && r.includes("_of_5")) {
    return "Compra virtual: se cumplieron las reglas del Bot Demo.";
  }
  return r.replace(/_/g, " ");
}

export function botNarrative(opts: {
  status?: string | null;
  lastReason?: string | null;
  lastAction?: string | null;
  lastSymbol?: string | null;
  openPositions?: number;
}): string {
  const st = (opts.status || "").toUpperCase();
  if (st === "STOPPED") {
    if ((opts.openPositions || 0) > 0) {
      return "El bot está detenido. No abrirá compras nuevas, pero sigue protegiendo las posiciones abiertas.";
    }
    return "El bot está detenido. No abrirá nuevas compras hasta que lo inicies.";
  }
  if (st === "RUNNING") {
    if (opts.lastAction === "BUY" && opts.lastSymbol) {
      return `Se ejecutó una compra virtual de ${opts.lastSymbol}.`;
    }
    if (opts.lastAction === "SELL" && opts.lastSymbol) {
      return `Se vendió una posición de ${opts.lastSymbol}.`;
    }
    if (opts.lastReason?.includes("insufficient") || opts.lastReason === "no_clear_signal") {
      return "Analizando BTC, ETH y SOL. Todavía no hay una señal suficientemente fuerte.";
    }
    return "El bot está en marcha y busca oportunidades en el mercado.";
  }
  return "Revisando el estado del sistema…";
}

export const METRIC_HELP = {
  cash: "Dinero libre para nuevas operaciones (simulación).",
  equity: "Saldo disponible más el valor actual de las posiciones abiertas.",
  realized: "Resultado de operaciones ya cerradas (compras y ventas completadas).",
  unrealized: "Resultado estimado si cerraras ahora las posiciones abiertas.",
  drawdown: "Cuánto ha retrocedido la cuenta desde su mejor punto.",
  signal: "El bot vio una posible oportunidad; no siempre significa que compró o vendió.",
  filled: "Una compra o venta virtual que sí se realizó en la cuenta de simulación.",
  paper: "Todo es simulación. No se usa dinero real ni se envían órdenes a Binance.",
} as const;
