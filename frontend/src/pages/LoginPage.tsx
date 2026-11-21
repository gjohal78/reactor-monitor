import { useState } from "react";
import type { SyntheticEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

export function LoginPage() {
  const { user, login, expired } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (user) return <Navigate to={from} replace />;

  const submit = async (event: SyntheticEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      void navigate(from, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed");
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login">
      <div className="panel login-panel">
        <h1>reactor-monitor</h1>
        <p className="login-intro">
          Sign in to watch the simulated reactor. Educational simulator, not a real safety system.
        </p>
        {expired ? <p className="message message-muted">Your session ended. Sign in again to continue.</p> : null}
        <form className="login-form" onSubmit={(e) => void submit(e)}>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
              }}
              required
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
              }}
              required
            />
          </div>
          {error ? (
            <p className="message message-error" role="alert">
              {error}
            </p>
          ) : null}
          <button type="submit" className="button button-primary" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
