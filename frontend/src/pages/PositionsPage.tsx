import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Position } from "../api";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusBadge } from "../components/ui/StatusBadge";
import { money, price, qty, when } from "../ui/format";
import { accountLabel } from "../ui/labels";

type AccountKey = "demo" | "paper";

export default function PositionsPage() {
  const [account, setAccount] = useState<AccountKey>("demo");
  const [paper, setPaper] = useState<Position[]>([]);
  const [demo, setDemo] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setError(null);
      const [p, d] = await Promise.all([
        api.positions(),
        api.demoStatus().catch(() => null),
      ]);
      setPaper(p);
      setDemo(((d?.positions as Array<Record<string, unknown>>) || []) as Array<
        Record<string, unknown>
      >);
    } catch {
      setError("No pudimos cargar las posiciones. Inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 15000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <p className="loading-block">Cargando posiciones…</p>;

  const rows =
    account === "demo"
      ? demo.map((p) => ({
          symbol: String(p.symbol),
          qty: Number(p.qty),
          entry: Number(p.entry_price),
          mark: Number(p.mark),
          upnl: Number(p.upnl),
          opened: null as string | null,
          stop: null as number | null,
          take: null as number | null,
        }))
      : paper.map((p) => ({
          symbol: p.symbol,
          qty: p.qty,
          entry: p.qty ? p.cost / p.qty : null,
          mark: p.price,
          upnl: p.unrealized_pnl ?? null,
          opened: null as string | null,
          stop: null as number | null,
          take: null as number | null,
        }));

  return (
    <div>
      <PageHeader
        title="Mis posiciones"
        subtitle="Lo que el bot tiene comprado ahora en la cuenta seleccionada. Todo es simulación."
        actions={
          <select
            className="account-select"
            value={account}
            onChange={(e) => setAccount(e.target.value as AccountKey)}
            aria-label="Cuenta"
          >
            <option value="demo">{accountLabel("demo_manual_control")}</option>
            <option value="paper">{accountLabel("sma_paper")}</option>
          </select>
        }
      />

      {error && <div className="error-box">{error}</div>}

      {!rows.length ? (
        <div className="panel">
          <EmptyState
            title="Sin posiciones abiertas"
            description="Cuando haya una compra virtual, verás aquí cantidad, precio y resultado estimado."
            icon="◎"
            action={
              <Link to="/demo" className="btn btn-primary">
                Ir al Bot Demo
              </Link>
            }
          />
        </div>
      ) : (
        <div className="position-cards">
          {rows.map((p) => {
            const upnl = p.upnl;
            const entry = p.entry;
            const mark = p.mark;
            let stopDist: string | null = null;
            let takeDist: string | null = null;
            if (entry && mark && entry > 0) {
              // Virtual 1% / 2% demo policy hint when API lacks explicit levels
              const stopLevel = p.stop ?? entry * 0.99;
              const takeLevel = p.take ?? entry * 1.02;
              stopDist = `${(((mark - stopLevel) / entry) * 100).toFixed(2)}% al stop`;
              takeDist = `${(((takeLevel - mark) / entry) * 100).toFixed(2)}% al objetivo`;
            }
            return (
              <div className="position-card" key={p.symbol}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <h4>{p.symbol.replace("USDT", "")}</h4>
                  <StatusBadge variant={(upnl ?? 0) >= 0 ? "ok" : "danger"}>
                    {(upnl ?? 0) >= 0 ? "En positivo" : "En negativo"}
                  </StatusBadge>
                </div>
                <div className="pos-row">
                  <span>Cantidad</span>
                  <strong>{qty(p.qty)}</strong>
                </div>
                <div className="pos-row">
                  <span>Precio de compra</span>
                  <strong>{price(entry)}</strong>
                </div>
                <div className="pos-row">
                  <span>Precio de mercado</span>
                  <strong>{price(mark)}</strong>
                </div>
                <div className="pos-row">
                  <span>Resultado estimado</span>
                  <strong style={{ color: (upnl ?? 0) >= 0 ? "var(--buy)" : "var(--sell)" }}>
                    {money(upnl, { signed: true })}
                  </strong>
                </div>
                {p.opened ? (
                  <div className="pos-row">
                    <span>Apertura</span>
                    <strong>{when(p.opened)}</strong>
                  </div>
                ) : null}
                {stopDist ? (
                  <div className="pos-row">
                    <span>Protección de pérdida</span>
                    <strong>{stopDist}</strong>
                  </div>
                ) : null}
                {takeDist ? (
                  <div className="pos-row">
                    <span>Objetivo de ganancia</span>
                    <strong>{takeDist}</strong>
                  </div>
                ) : null}
                <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                  El stop no garantiza el precio exacto de ejecución; depende de que el servicio esté
                  activo.
                </p>
                <Link
                  to={`/mercado?symbol=${encodeURIComponent(p.symbol)}`}
                  className="link-btn"
                >
                  Abrir gráfico
                </Link>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
