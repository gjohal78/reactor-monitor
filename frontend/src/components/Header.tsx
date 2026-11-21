import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { ROLE_LABEL } from "../auth/roles";
import type { ConnectionStatus as Status } from "../telemetry/useTelemetry";

/**
 * "Retrying in N s". Keyed by retryAt in ConnectionStatus, so each retry mounts a fresh
 * countdown whose clock starts now (a clock kept from earlier would show a stale number
 * for the first frame).
 */
function RetryCountdown({ retryAt }: { retryAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 250);
    return () => {
      clearInterval(timer);
    };
  }, []);
  const seconds = Math.max(0, Math.ceil((retryAt - now) / 1000));
  return <>{seconds > 0 ? `Connection lost. Retrying in ${String(seconds)} s` : "Reconnecting…"}</>;
}

function ConnectionStatus({ status, retryAt }: { status: Status; retryAt: number | null }) {
  let text: ReactNode = "Connecting…";
  if (status === "live") text = "Live";
  if (status === "reconnecting") {
    text = retryAt === null ? "Reconnecting…" : <RetryCountdown key={retryAt} retryAt={retryAt} />;
  }
  return (
    <div className={`connection connection-${status}`} role="status" data-testid="connection">
      <span className="dot" aria-hidden="true" />
      {text}
    </div>
  );
}

interface Props {
  status?: Status;
  retryAt?: number | null;
}

export function Header({ status, retryAt = null }: Props) {
  const { user, logout, can } = useAuth();
  return (
    <header className="header">
      <span className="brand">reactor-monitor</span>
      <nav className="nav" aria-label="Main">
        <NavLink to="/" end>
          Dashboard
        </NavLink>
        {can("supervisor") ? <NavLink to="/audit">Audit log</NavLink> : null}
      </nav>
      <div className="header-end">
        {status ? <ConnectionStatus status={status} retryAt={retryAt} /> : null}
        {user ? (
          <span className="user">
            {user.username}
            <span className="role" data-testid="role">
              {ROLE_LABEL[user.role]}
            </span>
          </span>
        ) : null}
        <button type="button" className="button-link" onClick={logout}>
          Sign out
        </button>
      </div>
    </header>
  );
}
