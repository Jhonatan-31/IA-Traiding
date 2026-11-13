import { FormEvent, ReactNode, useEffect, useState } from "react";
import {
  fetchAuthStatus,
  loginReadAccess,
  logoutReadAccess,
  type AuthStatus,
} from "../api";

/**
 * AH4 — Cuando DASHBOARD_READ_AUTH está OFF, no interpone pantalla.
 * Cuando está ON, exige sesión (cookie HttpOnly) antes del dashboard.
 * No persiste la clave de lectura en el almacenamiento del navegador.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");

  async function refresh() {
    try {
      const s = await fetchAuthStatus();
      setStatus(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo comprobar el acceso");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await loginReadAccess(token);
      setToken("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Acceso denegado");
    } finally {
      setBusy(false);
    }
  }

  async function onLogout() {
    setBusy(true);
    try {
      await logoutReadAccess();
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!status && !error) {
    return (
      <div className="loading-block">
        <p className="muted">Comprobando acceso…</p>
      </div>
    );
  }

  const enforced = Boolean(status?.read_auth?.enforced);
  const ok = status?.session_valid !== false;

  if (enforced && !ok) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          padding: 24,
          background: "linear-gradient(160deg, #0f1419 0%, #1a2332 55%, #243044 100%)",
          color: "#e8eef7",
        }}
      >
        <form
          onSubmit={onSubmit}
          style={{
            width: "min(420px, 100%)",
            display: "grid",
            gap: 14,
            padding: 28,
            borderRadius: 16,
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <div>
            <p style={{ margin: 0, letterSpacing: "0.12em", fontSize: 12, opacity: 0.7 }}>
              AI TRADING BOT PRO
            </p>
            <h1 style={{ margin: "8px 0 0", fontSize: 28, fontWeight: 650 }}>Acceso</h1>
            <p className="muted" style={{ marginTop: 8, lineHeight: 1.45 }}>
              Introduce la clave de lectura para ver el panel. No se guarda en el navegador de forma
              permanente.
            </p>
          </div>
          <label style={{ display: "grid", gap: 6, fontSize: 14 }}>
            Clave de lectura
            <input
              type="password"
              autoComplete="current-password"
              value={token}
              onChange={(ev) => setToken(ev.target.value)}
              required
              style={{
                padding: "12px 14px",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.15)",
                background: "rgba(0,0,0,0.25)",
                color: "inherit",
              }}
            />
          </label>
          {error ? (
            <p style={{ margin: 0, color: "#ffb4b4", fontSize: 14 }}>{error}</p>
          ) : null}
          <button className="btn primary" type="submit" disabled={busy || !token}>
            {busy ? "Verificando…" : "Entrar"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <>
      {enforced ? (
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 10,
            padding: "6px 16px",
            fontSize: 12,
            opacity: 0.85,
          }}
        >
          <span>Sesión de lectura activa</span>
          <button type="button" className="btn" disabled={busy} onClick={() => void onLogout()}>
            Cerrar sesión
          </button>
        </div>
      ) : null}
      {children}
    </>
  );
}
