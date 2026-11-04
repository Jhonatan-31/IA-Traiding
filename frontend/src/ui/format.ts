const TZ = "America/Bogota";

export function money(
  n: number | null | undefined,
  opts?: { digits?: number; unit?: string; signed?: boolean }
): string {
  if (n == null || Number.isNaN(n)) return "—";
  const digits = opts?.digits ?? 2;
  const unit = opts?.unit ?? "USDT";
  const signed = opts?.signed ?? false;
  const abs = Math.abs(n);
  const formatted = abs.toLocaleString("es-CO", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const sign = signed ? (n > 0 ? "+" : n < 0 ? "−" : "") : n < 0 ? "−" : "";
  return `${sign}${formatted} ${unit}`;
}

export function pct(
  n: number | null | undefined,
  opts?: { digits?: number; signed?: boolean }
): string {
  if (n == null || Number.isNaN(n)) return "—";
  const digits = opts?.digits ?? 2;
  const signed = opts?.signed ?? true;
  const abs = Math.abs(n).toLocaleString("es-CO", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const sign = signed ? (n > 0 ? "+" : n < 0 ? "−" : "") : n < 0 ? "−" : "";
  return `${sign}${abs}%`;
}

export function qty(n: number | null | undefined, digits = 6): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1) {
    return n.toLocaleString("es-CO", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });
  }
  return n.toLocaleString("es-CO", {
    minimumFractionDigits: Math.min(digits, 8),
    maximumFractionDigits: Math.min(digits, 8),
  });
}

export function price(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const digits = Math.abs(n) >= 100 ? 2 : Math.abs(n) >= 1 ? 4 : 6;
  return n.toLocaleString("es-CO", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function when(
  iso: string | null | undefined,
  opts?: { withDate?: boolean; withSeconds?: boolean }
): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-CO", {
    timeZone: TZ,
    day: opts?.withDate === false ? undefined : "2-digit",
    month: opts?.withDate === false ? undefined : "2-digit",
    year: opts?.withDate === false ? undefined : "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: opts?.withSeconds ? "2-digit" : undefined,
  });
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("es-CO", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function pnlTone(n: number | null | undefined): "pos" | "neg" | "neu" {
  if (n == null || Number.isNaN(n) || n === 0) return "neu";
  return n > 0 ? "pos" : "neg";
}
