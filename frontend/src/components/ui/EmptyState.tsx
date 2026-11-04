import type { ReactNode } from "react";

export function EmptyState(props: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: string;
}) {
  return (
    <div className="empty-state" role="status">
      {props.icon ? <div className="empty-icon" aria-hidden>{props.icon}</div> : null}
      <h3>{props.title}</h3>
      <p>{props.description}</p>
      {props.action ? <div className="empty-action">{props.action}</div> : null}
    </div>
  );
}
