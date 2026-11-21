import { useState } from "react";
import type { SyntheticEvent } from "react";

import type { RodEnvelope } from "../api/types";
import { formatPercent } from "../format";

interface Props {
  position: number | null;
  target: number | null;
  scrammed: boolean;
  envelope: RodEnvelope | null;
  canOperate: boolean;
  onMove: (target: number) => Promise<void>;
}

/**
 * Rod position (0 % = fully withdrawn, 100 % = fully inserted) and the target command.
 * The envelope checks here only give quicker feedback: the server enforces the same
 * limits and has the final say.
 */
export function RodControl({ position, target, scrammed, envelope, canOperate, onMove }: Props) {
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState<{ kind: "error" | "ok"; text: string } | null>(null);
  const [sending, setSending] = useState(false);

  const disabled = !canOperate || scrammed || target === null || sending;

  const validate = (value: number): string | null => {
    if (!Number.isFinite(value) || value < 0 || value > 100) return "Enter a target between 0 and 100 %.";
    if (envelope && value < envelope.min_insertion_percent) {
      return `Rods can't be withdrawn above ${formatPercent(envelope.min_insertion_percent, 0)} inserted.`;
    }
    if (envelope && target !== null && target - value > envelope.max_withdraw_step_percent + 1e-9) {
      return `One command can withdraw rods at most ${formatPercent(envelope.max_withdraw_step_percent, 0)}.`;
    }
    return null;
  };

  const send = async (value: number) => {
    const problem = validate(value);
    if (problem) {
      setMessage({ kind: "error", text: problem });
      return;
    }
    setSending(true);
    setMessage(null);
    try {
      await onMove(value);
      setMessage({ kind: "ok", text: `Rods moving to ${formatPercent(value)}` });
      setDraft("");
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : "The command was rejected" });
    } finally {
      setSending(false);
    }
  };

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    void send(Number(draft));
  };

  const nudge = (delta: number) => {
    if (target !== null) void send(Math.round((target + delta) * 10) / 10);
  };

  return (
    <section className="panel" aria-labelledby="rods-title">
      <h2 className="panel-title" id="rods-title">
        Control rods
      </h2>
      <div
        className="rod-bar"
        role="meter"
        aria-label="Rod insertion"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={position ?? undefined}
      >
        <div className="rod-fill" style={{ width: `${String(position ?? 0)}%` }} />
        {envelope ? (
          <div
            className="rod-limit"
            style={{ left: `${String(envelope.min_insertion_percent)}%` }}
            title="Minimum insertion"
          />
        ) : null}
        {target !== null ? (
          <div className="rod-target" style={{ left: `calc(${String(target)}% - 1px)` }} title="Target" />
        ) : null}
      </div>
      <div className="rod-scale">
        <span>Withdrawn</span>
        <span>Inserted</span>
      </div>
      <dl className="readouts" style={{ marginBottom: 14 }}>
        <dt>Position</dt>
        <dd data-testid="rod-position">{position === null ? "–" : formatPercent(position)}</dd>
        <dt>Target</dt>
        <dd>{target === null ? "–" : formatPercent(target)}</dd>
      </dl>

      {/* noValidate: show our own messages (which name the actual limit), not the browser's. */}
      <form className="rod-form" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="rod-target">New target (% inserted)</label>
          <input
            id="rod-target"
            className="input"
            type="number"
            inputMode="decimal"
            step="0.5"
            min={envelope?.min_insertion_percent ?? 0}
            max={100}
            placeholder={target === null ? "" : target.toFixed(1)}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            disabled={disabled}
          />
        </div>
        <button type="submit" className="button button-primary" disabled={disabled || draft === ""}>
          Move rods
        </button>
      </form>
      <div className="rod-nudges">
        <button type="button" className="button" disabled={disabled} onClick={() => {
            nudge(-1);
          }}>
          Withdraw 1 %
        </button>
        <button type="button" className="button" disabled={disabled} onClick={() => {
            nudge(1);
          }}>
          Insert 1 %
        </button>
      </div>

      {/* A "moving to" note from before a scram would be wrong now: the rods are locked in. */}
      {message && !(scrammed && message.kind === "ok") ? (
        <p
          className={`message ${message.kind === "error" ? "message-error" : "message-muted"}`}
          style={{ marginTop: 10 }}
          role={message.kind === "error" ? "alert" : "status"}
        >
          {message.text}
        </p>
      ) : null}
      {!canOperate ? (
        <p className="control-note">Operators and supervisors can move rods. You're signed in as a viewer.</p>
      ) : scrammed ? (
        <p className="control-note">Rods are locked in while the reactor is scrammed.</p>
      ) : envelope ? (
        <p className="control-note">
          Limits: at least {formatPercent(envelope.min_insertion_percent, 0)} inserted; withdraw at most{" "}
          {formatPercent(envelope.max_withdraw_step_percent, 0)} per command. Inserting is never limited.
        </p>
      ) : null}
    </section>
  );
}
