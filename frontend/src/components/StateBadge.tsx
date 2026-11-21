import type { AlarmState } from "../api/types";
import { ALARM_STATE_LABEL, severity } from "../format";

/** Alarm state as shape + label + colour, never colour alone. */
export function StateIcon({ state }: { state: AlarmState }) {
  const sev = severity(state);
  if (sev === "unacked") {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M7 1 13 12.5H1Z" fill="currentColor" />
      </svg>
    );
  }
  if (sev === "acked") {
    return (
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
        <path d="M7 1 13 12.5H1Z" fill="none" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

export function StateBadge({ state }: { state: AlarmState }) {
  return (
    <span className={`state state-${severity(state)}`}>
      <StateIcon state={state} />
      {ALARM_STATE_LABEL[state]}
    </span>
  );
}
