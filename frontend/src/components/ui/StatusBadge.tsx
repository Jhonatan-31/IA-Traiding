type Variant = "ok" | "warn" | "danger" | "info" | "neutral" | "buy" | "sell";

export function StatusBadge(props: {
  children: React.ReactNode;
  variant?: Variant;
  pulse?: boolean;
}) {
  const v = props.variant || "neutral";
  return (
    <span className={`status-badge status-${v}${props.pulse ? " is-pulse" : ""}`}>
      <span className="status-dot" aria-hidden />
      {props.children}
    </span>
  );
}
