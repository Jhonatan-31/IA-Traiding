import type { ReactNode } from "react";

export function PageHeader(props: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        {props.eyebrow ? <p className="page-eyebrow">{props.eyebrow}</p> : null}
        <h1>{props.title}</h1>
        {props.subtitle ? <p className="page-subtitle">{props.subtitle}</p> : null}
      </div>
      {props.actions ? <div className="page-header-actions">{props.actions}</div> : null}
    </header>
  );
}
