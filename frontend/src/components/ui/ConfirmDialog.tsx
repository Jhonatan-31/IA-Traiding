import type { ReactNode } from "react";

export function ConfirmDialog(props: {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!props.open) return null;
  return (
    <div className="dialog-backdrop" role="presentation" onClick={props.onCancel}>
      <div
        className="dialog-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-title">{props.title}</h2>
        <div className="dialog-body">{props.children}</div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={props.onCancel} disabled={props.busy}>
            {props.cancelLabel || "Cancelar"}
          </button>
          <button
            type="button"
            className={`btn ${props.danger ? "btn-danger" : "btn-primary"}`}
            onClick={props.onConfirm}
            disabled={props.busy}
          >
            {props.busy ? "Esperando…" : props.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
