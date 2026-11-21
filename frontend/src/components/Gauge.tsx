import type { Severity } from "../format";

interface Props {
  label: string;
  value: number | null;
  unit: string;
  min: number;
  max: number;
  limit?: number;
  digits?: number;
  /** Alarm state for this quantity; colours the arc and value only when abnormal. */
  status: Severity;
}

const CX = 120;
const CY = 118;
const R = 92;
const SWEEP = 240; // degrees, from lower-left round to lower-right

function polar(t: number, radius = R): [number, number] {
  const angle = ((210 - SWEEP * t) * Math.PI) / 180;
  return [CX + radius * Math.cos(angle), CY - radius * Math.sin(angle)];
}

function arc(from: number, to: number): string {
  const [x1, y1] = polar(from);
  const [x2, y2] = polar(to);
  const large = (to - from) * SWEEP > 180 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${String(R)} ${String(R)} 0 ${String(large)} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

const STATUS_COLOR: Record<Severity, string> = {
  unacked: "var(--critical)",
  acked: "var(--warning)",
  cleared: "var(--ink-2)",
  normal: "var(--ink-2)",
};

const STATUS_TEXT: Partial<Record<Severity, string>> = {
  unacked: "Alarm, not acknowledged",
  acked: "Alarm acknowledged",
};

export function Gauge({ label, value, unit, min, max, limit, digits = 1, status }: Props) {
  const fraction = value === null ? 0 : Math.min(1, Math.max(0, (value - min) / (max - min)));
  const limitFraction = limit === undefined ? null : (limit - min) / (max - min);
  const color = STATUS_COLOR[status];
  const statusText = STATUS_TEXT[status];

  return (
    <figure className="gauge" style={{ margin: 0 }}>
      <svg
        viewBox="0 0 240 190"
        role="meter"
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value ?? undefined}
        aria-valuetext={value === null ? "No data" : `${value.toFixed(digits)} ${unit}`}
      >
        <path d={arc(0, 1)} fill="none" stroke="var(--line-strong)" strokeWidth="12" strokeLinecap="round" />
        {value !== null && fraction > 0.002 ? (
          <path d={arc(0, fraction)} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round" />
        ) : null}
        {limitFraction !== null && limitFraction >= 0 && limitFraction <= 1 ? (
          <LimitTick fraction={limitFraction} limit={limit ?? 0} />
        ) : null}
        <text x={CX} y={CY + 4} textAnchor="middle" className="gauge-value">
          {value === null ? "–" : value.toFixed(digits)}
        </text>
        <text x={CX} y={CY + 26} textAnchor="middle" className="gauge-unit">
          {unit}
        </text>
        <text x={polar(0, R)[0]} y={CY + 64} textAnchor="middle" className="gauge-scale">
          {min}
        </text>
        <text x={polar(1, R)[0]} y={CY + 64} textAnchor="middle" className="gauge-scale">
          {max}
        </text>
      </svg>
      <figcaption style={{ textAlign: "center" }}>
        <div>{label}</div>
        <div className={`gauge-status ${statusText ? `gauge-status-${status}` : ""}`}>
          {statusText ?? (limit !== undefined ? `Alarm above ${String(limit)} ${unit}` : " ")}
        </div>
      </figcaption>
    </figure>
  );
}

function LimitTick({ fraction, limit }: { fraction: number; limit: number }) {
  const [x1, y1] = polar(fraction, R - 12);
  const [x2, y2] = polar(fraction, R + 12);
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke="var(--warning)"
      strokeWidth="3"
      data-limit={limit}
    />
  );
}
