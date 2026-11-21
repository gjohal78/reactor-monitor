import { memo, useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { niceTicks } from "../chartTicks";
import { formatClock } from "../format";
import type { TrendPoint } from "../telemetry/trend";

interface Props {
  title: string;
  data: TrendPoint[];
  dataKey: "power" | "temp";
  unit: string;
  limit?: number;
  /** Lower/upper bound the y-axis always includes (it grows to fit larger values). */
  domain: [number, number];
}

const AXIS = { stroke: "#383d45", tick: { fill: "#9aa3ad", fontSize: 12 } };

/** Seconds on the axis while the window is short, otherwise hours and minutes. */
function timeFormatter(spanMs: number) {
  const options: Intl.DateTimeFormatOptions =
    spanMs < 5 * 60_000
      ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
      : { hour: "2-digit", minute: "2-digit" };
  return (t: number) => new Date(t).toLocaleTimeString([], options);
}

/**
 * One quantity per chart: power and temperature have different units, so no dual axis.
 *
 * Memoised: telemetry arrives at 10 Hz but the trend buffer only gains a point once a
 * second (appendLive returns the same array otherwise), so the chart redraws ~900 points
 * once a second instead of ten times. `domain` must be a stable reference for this.
 */
export const TrendChart = memo(function TrendChart({ title, data, dataKey, unit, limit, domain }: Props) {
  const titleId = `trend-${dataKey}`;
  const { ticks, formatTime } = useMemo(() => {
    const values = data.map((p) => p[dataKey]);
    const low = Math.min(domain[0], ...values);
    const high = Math.max(domain[1], ...values);
    const span = (data.at(-1)?.t ?? 0) - (data[0]?.t ?? 0);
    return { ticks: niceTicks(low, high), formatTime: timeFormatter(span) };
  }, [data, dataKey, domain]);
  return (
    <section className="panel" aria-labelledby={titleId}>
      <h2 className="panel-title" id={titleId}>
        {title}, last 15 minutes
      </h2>
      {data.length < 2 ? (
        <div className="chart-empty">Waiting for data…</div>
      ) : (
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="#262b32" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                domain={["dataMin", "dataMax"]}
                scale="time"
                tickFormatter={formatTime}
                minTickGap={56}
                {...AXIS}
              />
              <YAxis
                domain={[ticks[0] ?? domain[0], ticks.at(-1) ?? domain[1]]}
                ticks={ticks}
                interval={0}
                width={48}
                tickFormatter={(v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1))}
                {...AXIS}
              />
              {limit !== undefined ? (
                <ReferenceLine
                  y={limit}
                  stroke="var(--warning)"
                  strokeDasharray="6 4"
                  label={{
                    value: `Alarm ${String(limit)} ${unit}`,
                    position: "insideTopRight",
                    fill: "#fab219",
                    fontSize: 12,
                  }}
                />
              ) : null}
              <Tooltip
                cursor={{ stroke: "#6b737d", strokeWidth: 1 }}
                isAnimationActive={false}
                content={({ active, payload }) => {
                  const p = payload[0]?.payload as TrendPoint | undefined;
                  if (!active || !p) return null;
                  return (
                    <div className="chart-tooltip">
                      <div className="chart-tooltip-time">{formatClock(p.t)}</div>
                      <div>
                        {p[dataKey].toFixed(1)} {unit}
                      </div>
                    </div>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey={dataKey}
                stroke="var(--trend)"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: "#171b21", strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
});
