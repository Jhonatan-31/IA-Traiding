import type { ReactNode } from "react";

export type FeedItem = {
  id: string;
  time: string;
  title: string;
  detail?: string;
  tone?: "buy" | "sell" | "hold" | "info" | "warn";
  meta?: ReactNode;
  onExplain?: () => void;
};

export function ActivityFeed(props: {
  items: FeedItem[];
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  if (!props.items.length) {
    return (
      <div className="empty-state compact">
        <h3>{props.emptyTitle || "Sin actividad todavía"}</h3>
        <p>{props.emptyDescription || "Cuando el bot analice el mercado, verás aquí lo que ocurre."}</p>
      </div>
    );
  }
  return (
    <ul className="activity-feed">
      {props.items.map((it) => (
        <li key={it.id} className={`feed-item feed-${it.tone || "info"}`}>
          <div className="feed-time tabular">{it.time}</div>
          <div className="feed-body">
            <div className="feed-title">{it.title}</div>
            {it.detail ? <div className="feed-detail">{it.detail}</div> : null}
            {it.meta}
            {it.onExplain ? (
              <button type="button" className="link-btn" onClick={it.onExplain}>
                ¿Por qué tomó esta decisión?
              </button>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
