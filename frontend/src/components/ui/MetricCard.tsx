import type { ReactNode } from "react";

type Tone = "default" | "pos" | "neg" | "brand" | "warn";

export function MetricCard(props: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  sub?: ReactNode;
}) {
  const tone = props.tone || "default";
  return (
    <div className={`metric-card metric-${tone}`}>
      <div className="metric-label">
        <span>{props.label}</span>
        {props.hint ? (
          <span className="info-tip" title={props.hint} aria-label={props.hint}>
            ?
          </span>
        ) : null}
      </div>
      <div className="metric-value tabular">{props.value}</div>
      {props.sub ? <div className="metric-sub">{props.sub}</div> : null}
    </div>
  );
}
