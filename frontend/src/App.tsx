import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "./api/health";

type HealthState =
  | { kind: "loading" }
  | { kind: "ok"; data: HealthResponse }
  | { kind: "error"; message: string };

export default function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(fetch, controller.signal)
      .then((data) => {
        setHealth({ kind: "ok", data });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setHealth({ kind: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <main className="page">
      <header>
        <h1>reactor-monitor</h1>
        <p className="disclaimer">
          Educational simulator. Not a real reactor safety system.
        </p>
      </header>

      <section className="card" aria-live="polite">
        <h2>Backend status</h2>
        {health.kind === "loading" && <p>Checking…</p>}
        {health.kind === "ok" && (
          <p className="status ok">
            ● Online — {health.data.service} v{health.data.version} ({health.data.environment})
          </p>
        )}
        {health.kind === "error" && <p className="status error">● Offline — {health.message}</p>}
      </section>
    </main>
  );
}
