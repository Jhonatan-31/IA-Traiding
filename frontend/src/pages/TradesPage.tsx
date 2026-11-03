import { useEffect, useState } from "react";
import { api, fmtNum, fmtTime, type Trade } from "../api";

export default function TradesPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setTrades(await api.trades(200));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error");
      }
    })();
  }, []);

  function exportCsv() {
    const headers = [
      "id",
      "at",
      "symbol",
      "side",
      "qty",
      "price",
      "candle_ms",
      "fee_rate",
      "slip_rate",
      "strategy",
      "reason",
    ];
    const lines = [
      headers.join(","),
      ...trades.map((t) => {
        const row = t as unknown as Record<string, unknown>;
        return headers
          .map((h) => JSON.stringify(String(row[h] ?? "")))
          .join(",");
      }),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "trades_paper.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Operaciones</h2>
          <p>Historial de fills simulados. No son órdenes reales.</p>
        </div>
        <button className="btn primary" onClick={exportCsv} disabled={!trades.length}>
          Exportar CSV
        </button>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="card table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>ID</th>
              <th>Fecha</th>
              <th>Mercado</th>
              <th>Dirección</th>
              <th>Cantidad</th>
              <th>Precio fill</th>
              <th>Fee</th>
              <th>Slip</th>
              <th>Estrategia</th>
              <th>Motivo</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={10} className="muted">
                  Sin registros todavía.
                </td>
              </tr>
            ) : (
              trades.map((t) => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td>{fmtTime(t.at)}</td>
                  <td>{t.symbol}</td>
                  <td>{t.side}</td>
                  <td>{fmtNum(t.qty, 8)}</td>
                  <td>{fmtNum(t.price, 6)}</td>
                  <td>{t.fee_rate == null ? "Sin datos" : fmtNum(t.fee_rate, 4)}</td>
                  <td>{t.slip_rate == null ? "Sin datos" : fmtNum(t.slip_rate, 4)}</td>
                  <td>{t.strategy ?? "Sin datos"}</td>
                  <td>{t.reason ?? "Sin datos"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
