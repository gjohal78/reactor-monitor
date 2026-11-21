import { useEffect, useRef, useState } from "react";

import { formatPercent } from "../format";

interface Props {
  scrammed: boolean;
  rodPosition: number | null;
  canScram: boolean;
  canReset: boolean;
  onScram: () => Promise<void>;
  onReset: () => Promise<void>;
}

const COVER_TIMEOUT_MS = 10_000;

/**
 * SCRAM as a guarded switch, like the flip-up cover over a real trip button: lift the
 * cover, then press SCRAM. The cover closes again by itself after 10 s, or on Escape,
 * so the button is never left armed.
 */
export function ScramControl({ scrammed, rodPosition, canScram, canReset, onScram, onReset }: Props) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scramButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!armed) return;
    scramButton.current?.focus();
    const timer = setTimeout(() => {
      setArmed(false);
    }, COVER_TIMEOUT_MS);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setArmed(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", onKey);
    };
  }, [armed]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      setArmed(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The command failed");
    } finally {
      setBusy(false);
    }
  };

  const rodsIn = rodPosition !== null && rodPosition >= 100;

  return (
    <section className="panel scram" aria-labelledby="scram-title">
      <h2 className="panel-title" id="scram-title" style={{ marginBottom: 2 }}>
        Reactor trip
      </h2>

      {scrammed ? (
        <>
          <div className="scram-state" role="status">
            Scrammed. Rods {rodsIn ? "fully inserted" : `inserting: ${formatPercent(rodPosition ?? 0)}`}.
          </div>
          {canReset ? (
            <button
              type="button"
              className="button"
              disabled={!rodsIn || busy}
              onClick={() => void run(onReset)}
            >
              {busy ? "Resetting…" : "Reset scram"}
            </button>
          ) : (
            <p className="control-note" style={{ margin: 0 }}>
              A supervisor can reset the scram once the rods are fully in.
            </p>
          )}
          {canReset && !rodsIn ? (
            <p className="control-note" style={{ margin: 0 }}>
              Reset becomes available when the rods reach 100 %.
            </p>
          ) : null}
        </>
      ) : armed ? (
        <div className="scram-armed">
          <button
            ref={scramButton}
            type="button"
            className="scram-button"
            disabled={busy}
            onClick={() => void run(onScram)}
          >
            {busy ? "Scramming…" : "SCRAM"}
          </button>
          <button
            type="button"
            className="button"
            onClick={() => {
              setArmed(false);
            }}
          >
            Close cover
          </button>
          <p className="control-note" style={{ margin: 0 }}>
            Drives all rods fully in. The cover closes by itself after 10 seconds.
          </p>
        </div>
      ) : (
        <>
          <button
            type="button"
            className="scram-cover"
            disabled={!canScram}
            onClick={() => {
              setArmed(true);
            }}
          >
            Lift cover to SCRAM
          </button>
          {!canScram ? (
            <p className="control-note" style={{ margin: 0 }}>
              Operators and supervisors can scram the reactor.
            </p>
          ) : null}
        </>
      )}
      {error ? (
        <p className="message message-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
