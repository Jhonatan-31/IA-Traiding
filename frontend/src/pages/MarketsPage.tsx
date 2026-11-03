import { useEffect, useMemo, useState } from "react";
import { api, fmtNum, fmtTime, type Market } from "../api";

export default function MarketsPage() {
  const [rows, setRows] = useState<Market[]>([]);
  const [q, setQ] = useState("");
  const [onlyPos, setOnlyPos] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setRows(await api.markets());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error");
      }
    })();
  }, []);

  const filtered = useMemo(() => {
    return rows
      .filter((r) => (onlyPos ? r.has_position : true))
      .filter((r) => r.symbol.toLowerCase().includes(q.toLowerCase()))
      .sort((a, b) => a.symbol.localeCompare(b.symbol));
  }, [rows, q, onlyPos]);

  return (
    <div>
      <div className="page-title">
        <div>
          <h2>Mercados</h2>
          <p>
            Precios persistidos por el recolector. Variación 24h / liquidez
            avanzada: Sin datos hasta ampliar el backend.
          </p>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      <div className="actions" style={{ marginBottom: 14 }}>
        <input
          className="btn"
          style={{ minWidth: 220 }}
          placeholder="Buscar símbolo…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button className="btn" onClick={() => setOnlyPos((v) => !v)}>
          {onlyPos ? "Ver todos" : "Solo con posición"}
        </button>
      </div>
      <div className="card table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Símbolo</th>
              <th>Precio</th>
              <th>Fuente</th>
              <th>Posición</th>
              <th>Actualizado</th>
              <th>Var 24h</th>
              <th>Volumen</th>
              <th>Señal</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="muted">
                  Sin datos
                </td>
              </tr>
            ) : (
              filtered.map((m) => (
                <tr key={m.symbol}>
                  <td>{m.symbol}</td>
                  <td>{fmtNum(m.price, 6)}</td>
                  <td>{m.source ?? "Sin datos"}</td>
                  <td>{m.has_position ? "Sí" : "No"}</td>
                  <td>{fmtTime(m.at)}</td>
                  <td>Sin datos</td>
                  <td>Sin datos</td>
                  <td>Sin datos</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
