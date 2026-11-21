import type { Alarm } from "../api/types";
import { formatAlarmValue } from "../format";
import { StateIcon } from "./StateBadge";

interface Props {
  alarms: Alarm[];
  scrammed: boolean;
}

/**
 * One line under the header that always says the most important thing: a flashing red
 * bar while anything is unacknowledged (ISA-18.2: unacknowledged alarms flash,
 * acknowledged ones are steady), amber while acknowledged alarms are still active, and
 * a calm line otherwise. It keeps its place on screen so the layout never jumps.
 */
export function AlarmBanner({ alarms, scrammed }: Props) {
  const unacked = alarms.filter((a) => a.state === "ACTIVE_UNACKED" || a.state === "CLEARED_UNACKED");
  const active = alarms.filter((a) => a.state === "ACTIVE_UNACKED" || a.state === "ACTIVE_ACKED");
  const newest = unacked.at(-1);

  let tone = "";
  let text: string;
  if (newest) {
    tone = "banner-unacked";
    const more = unacked.length > 1 ? ` (+${String(unacked.length - 1)} more to acknowledge)` : "";
    text = `${newest.description}: ${formatAlarmValue(newest.trigger_value, newest.unit)}, limit ${formatAlarmValue(newest.limit, newest.unit)}${more}`;
  } else if (active.length > 0) {
    tone = "banner-acked";
    text = `${String(active.length)} acknowledged ${active.length === 1 ? "alarm" : "alarms"} still active`;
  } else if (scrammed) {
    tone = "banner-scrammed";
    text = "Reactor scrammed. Rods held fully in until a supervisor resets.";
  } else {
    text = "No active alarms";
  }

  return (
    <div className={`banner ${tone}`} role="status" aria-live="assertive" data-testid="alarm-banner">
      {newest ? (
        <span className="banner-icon">
          <StateIcon state={newest.state} />
        </span>
      ) : null}
      <span>{text}</span>
    </div>
  );
}
