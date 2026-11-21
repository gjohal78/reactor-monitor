import { useEffect, useState } from "react";

import { getAudit } from "../api/endpoints";
import type { AuditAction, AuditEntry } from "../api/types";
import { Header } from "../components/Header";
import { formatDateTime } from "../format";

const PAGE_SIZE = 50;

const ACTION_LABEL: Record<AuditAction, string> = {
  LOGIN: "Sign-in",
  ALARM_ACK: "Alarm acknowledged",
  ROD_MOVE: "Rods moved",
  SCRAM: "Scram",
  SCRAM_RESET: "Scram reset",
  ALARM_LIMITS_CHANGE: "Alarm limits changed",
  ACCESS_DENIED: "Access denied",
};

function show(value: unknown): string {
  return typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
}

function describeChange(entry: AuditEntry): string | null {
  const { old_value: before, new_value: after } = entry;
  if (!after) return null;
  const keys = Object.keys(after);
  const parts = keys.map((key) => {
    const from = before && key in before ? show(before[key]) : null;
    const to = show(after[key]);
    return from !== null && from !== to ? `${key}: ${from} → ${to}` : `${key}: ${to}`;
  });
  return parts.join(", ");
}

export function AuditPage() {
  const [page, setPage] = useState(0);
  const [action, setAction] = useState<AuditAction | "">("");
  const [username, setUsername] = useState("");
  const [appliedUser, setAppliedUser] = useState("");
  // The result remembers which query it answers; while it doesn't match, we're loading.
  const query = `${String(page)}|${action}|${appliedUser}`;
  const [result, setResult] = useState<{ query: string; entries: AuditEntry[]; error: string | null }>({
    query: "",
    entries: [],
    error: null,
  });
  const loading = result.query !== query;
  const { entries, error } = result;

  useEffect(() => {
    let cancelled = false;
    getAudit({
      limit: PAGE_SIZE + 1, // one extra to know whether there is a next page
      offset: page * PAGE_SIZE,
      action: action || undefined,
      username: appliedUser || undefined,
    })
      .then((rows) => {
        if (!cancelled) setResult({ query, entries: rows, error: null });
      })
      .catch((e: unknown) => {
        const message = e instanceof Error ? e.message : "Could not load the audit log";
        if (!cancelled) setResult({ query, entries: [], error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [page, action, appliedUser, query]);

  const visible = entries.slice(0, PAGE_SIZE);
  const hasNext = entries.length > PAGE_SIZE;

  return (
    <div className="shell">
      <Header />
      <div />
      <main className="page">
        <section className="panel" aria-labelledby="audit-title">
          <h1 className="panel-title" id="audit-title" style={{ fontSize: 18, color: "var(--ink)" }}>
            Audit log
          </h1>
          <form
            className="filters"
            onSubmit={(e) => {
              e.preventDefault();
              setPage(0);
              setAppliedUser(username.trim());
            }}
          >
            <div className="field">
              <label htmlFor="audit-action">Action</label>
              <select
                id="audit-action"
                className="input"
                value={action}
                onChange={(e) => {
                  setPage(0);
                  setAction(e.target.value as AuditAction | "");
                }}
              >
                <option value="">All actions</option>
                {(Object.keys(ACTION_LABEL) as AuditAction[]).map((a) => (
                  <option key={a} value={a}>
                    {ACTION_LABEL[a]}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="audit-user">Username</label>
              <input
                id="audit-user"
                className="input"
                value={username}
                onChange={(e) => {
                  setUsername(e.target.value);
                }}
                placeholder="Any user"
              />
            </div>
            <button type="submit" className="button">
              Apply
            </button>
          </form>

          {error ? <p className="message message-error">{error}</p> : null}
          {!loading && !error && visible.length === 0 ? (
            <p className="empty">No entries match these filters.</p>
          ) : null}
          {visible.length > 0 ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>User</th>
                    <th>Action</th>
                    <th>Result</th>
                    <th>Details</th>
                    <th>From</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((entry) => (
                    <tr key={entry.id}>
                      <td style={{ whiteSpace: "nowrap" }}>{formatDateTime(entry.timestamp)}</td>
                      <td>
                        {entry.username || "–"}
                        {entry.role ? <div className="message-muted">{entry.role}</div> : null}
                      </td>
                      <td>{ACTION_LABEL[entry.action]}</td>
                      <td className={entry.success ? "result-ok" : "result-fail"}>
                        {entry.success ? "✓ Succeeded" : "✗ Refused"}
                      </td>
                      <td className="change">
                        {entry.target ? <div>{entry.target}</div> : null}
                        {describeChange(entry) ? <code>{describeChange(entry)}</code> : null}
                        {entry.detail ? <div>{entry.detail}</div> : null}
                      </td>
                      <td className="message-muted">{entry.client_ip ?? "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="pager">
            <span>Page {page + 1}</span>
            <button type="button" className="button" disabled={page === 0} onClick={() => {
                setPage(page - 1);
              }}>
              Newer
            </button>
            <button type="button" className="button" disabled={!hasNext} onClick={() => {
                setPage(page + 1);
              }}>
              Older
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
