import { useEffect, useMemo, useState } from "react";
import { api, type Trade } from "../api";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { money, price, qty, when } from "../ui/format";
import { actionLabel, reasonLabel } from "../ui/labels";

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [side, setSide] = useState("");
  const [selected, setSelected] = useState<Trade | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setTrades(await api.trades(200));
      } catch {
        setError("No pudimos cargar el historial de movimientos.");
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    return trades.filter((t) => {
      if (side && t.side.toUpperCase() !== side) return false;
      if (q) {
        const hay = `${t.symbol} ${t.reason || ""} ${t.strategy || ""}`.toLowerCase();
        if (!hay.includes(q.toLowerCase())) return false;
      }
      return true;
    });
  }, [trades, q, side]);

  function exportCsv() {
    const headers = [
      "fecha",
      "mercado",
      "accion",
      "cantidad",
      "precio",
      "comision",
      "motivo",
    ];
    const lines = [
      headers.join(","),
      ...filtered.map((t) =>
        [
          t.at,
          t.symbol,
          t.side,
          t.qty,
          t.price,
          t.fee_rate ?? "",
          JSON.stringify(String(t.reason ?? "")),
        ].join(",")
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "movimientos_simulacion.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <PageHeader
        title="Movimientos"
        subtitle="Historial de compras y ventas virtuales de la cuenta papel principal. No son órdenes reales."
        actions={
          <button className="btn btn-primary" onClick={exportCsv} disabled={!filtered.length}>
            Exportar
          </button>
        }
      />
      {error && <div className="error-box">{error}</div>}

      <div className="filter-bar">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar mercado o motivo…"
          aria-label="Buscar movimientos"
        />
        <select value={side} onChange={(e) => setSide(e.target.value)} aria-label="Filtrar tipo">
          <option value="">Compras y ventas</option>
          <option value="BUY">Solo compras</option>
          <option value="SELL">Solo ventas</option>
        </select>
      </div>

      <div className="two-col">
        <div className="panel table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Fecha y hora</th>
                <th>Mercado</th>
                <th>Qué ocurrió</th>
                <th>Precio</th>
                <th>Cantidad</th>
                <th>Importe</th>
                <th>Motivo</th>
              </tr>
            </thead>
            <tbody>
              {!filtered.length ? (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      title="Sin operaciones todavía"
                      description="Cuando el motor ejecute compras o ventas virtuales, aparecerán aquí con detalle."
                    />
                  </td>
                </tr>
              ) : (
                filtered.map((t) => {
                  const act = t.side.toUpperCase();
                  const what = act === "BUY" ? "Compra completada" : "Venta completada";
                  return (
                    <tr
                      key={t.id}
                      onClick={() => setSelected(t)}
                      style={{ cursor: "pointer" }}
                      className={selected?.id === t.id ? "is-selected" : undefined}
                    >
                      <td className="tabular">{when(t.at)}</td>
                      <td>{t.symbol.replace("USDT", "")}</td>
                      <td style={{ color: act === "BUY" ? "var(--buy)" : "var(--sell)" }}>
                        {act === "BUY" ? "▲ " : "▼ "}
                        {what}
                      </td>
                      <td className="tabular">{price(t.price)}</td>
                      <td className="tabular">{qty(t.qty)}</td>
                      <td className="tabular">{money(t.qty * t.price)}</td>
                      <td style={{ whiteSpace: "normal", maxWidth: 220 }}>
                        {reasonLabel(t.reason)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h3 style={{ marginTop: 0, color: "var(--text)" }}>Detalle</h3>
          {!selected ? (
            <p className="muted">Selecciona un movimiento para ver el detalle.</p>
          ) : (
            <>
              <div className="pos-row">
                <span>Mercado</span>
                <strong>{selected.symbol}</strong>
              </div>
              <div className="pos-row">
                <span>Acción</span>
                <strong>{actionLabel(selected.side)}</strong>
              </div>
              <div className="pos-row">
                <span>Cantidad</span>
                <strong>{qty(selected.qty)}</strong>
              </div>
              <div className="pos-row">
                <span>Precio</span>
                <strong>{price(selected.price)}</strong>
              </div>
              <div className="pos-row">
                <span>Importe</span>
                <strong>{money(selected.qty * selected.price)}</strong>
              </div>
              <div className="pos-row">
                <span>Comisión (tasa)</span>
                <strong>
                  {selected.fee_rate == null ? "—" : `${(selected.fee_rate * 100).toFixed(3)}%`}
                </strong>
              </div>
              <div className="pos-row">
                <span>Diferencia de ejecución</span>
                <strong>
                  {selected.slip_rate == null ? "—" : `${(selected.slip_rate * 100).toFixed(3)}%`}
                </strong>
              </div>
              <p className="muted" style={{ marginTop: 12, lineHeight: 1.45 }}>
                {reasonLabel(selected.reason)}
              </p>
              <p className="muted" style={{ fontSize: 11 }}>
                Operación virtual ejecutada · {when(selected.at)}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
