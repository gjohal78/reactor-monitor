import { memo, useState } from "react";

import type { Alarm } from "../api/types";
import { formatAlarmValue, formatClock } from "../format";
import { StateBadge } from "./StateBadge";

interface Props {
  alarms: Alarm[];
  canAck: boolean;
  onAck: (id: string) => Promise<void>;
}

/** Memoised: the alarm array keeps its identity until an alarm actually changes. */
export const AlarmList = memo(function AlarmList({ alarms, canAck, onAck }: Props) {
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ack = async (id: string) => {
    setPending(id);
    setError(null);
    try {
      await onAck(id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not acknowledge the alarm");
    } finally {
      setPending(null);
    }
  };

  return (
    <section className="panel" aria-labelledby="alarms-title">
      <h2 className="panel-title" id="alarms-title">
        Alarms
      </h2>
      {alarms.length === 0 ? (
        <p className="empty">No active alarms. New alarms appear here as soon as a limit is crossed.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>State</th>
                <th>Alarm</th>
                <th>Value</th>
                <th>Limit</th>
                <th>Raised</th>
                {canAck ? <th aria-label="Actions" /> : null}
              </tr>
            </thead>
            <tbody>
              {alarms.map((alarm) => {
                const needsAck = alarm.state === "ACTIVE_UNACKED" || alarm.state === "CLEARED_UNACKED";
                return (
                  <tr key={alarm.id}>
                    <td>
                      <StateBadge state={alarm.state} />
                    </td>
                    <td>{alarm.description}</td>
                    <td>{formatAlarmValue(alarm.trigger_value, alarm.unit)}</td>
                    <td>{formatAlarmValue(alarm.limit, alarm.unit)}</td>
                    <td>{formatClock(alarm.activated_at)}</td>
                    {canAck ? (
                      <td>
                        {needsAck ? (
                          <button
                            type="button"
                            className="button"
                            disabled={pending === alarm.id}
                            onClick={() => void ack(alarm.id)}
                          >
                            {pending === alarm.id ? "Acknowledging…" : "Acknowledge"}
                          </button>
                        ) : null}
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {error ? <p className="message message-error">{error}</p> : null}
      {!canAck && alarms.length > 0 ? (
        <p className="control-note">Operators and supervisors can acknowledge alarms.</p>
      ) : null}
    </section>
  );
});
