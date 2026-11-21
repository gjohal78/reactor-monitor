/**
 * Trend buffer for the charts: one point per second over a rolling window.
 *
 * History (persisted once a second) seeds the buffer whenever the WebSocket (re)connects,
 * which also fills any gap left by a dropped connection. Live telemetry arrives at 10 Hz;
 * only one sample per second is kept, which matches the stored history and keeps the
 * charts at ~900 points for 15 minutes.
 */
import type { Reading, Telemetry } from "../api/types";

export interface TrendPoint {
  t: number; // epoch ms
  power: number;
  temp: number;
}

export const TREND_WINDOW_MS = 15 * 60 * 1000;
export const SAMPLE_SPACING_MS = 1000;

function point(sample: Reading | Telemetry): TrendPoint {
  return {
    t: Date.parse(sample.timestamp),
    power: sample.power_percent,
    temp: sample.coolant_temp_c,
  };
}

function trim(points: TrendPoint[], now: number, windowMs: number): TrendPoint[] {
  const cutoff = now - windowMs;
  const first = points.findIndex((p) => p.t >= cutoff);
  return first <= 0 ? points : points.slice(first);
}

/** Replace the buffer with history, keeping any live points newer than the history. */
export function mergeHistory(
  current: TrendPoint[],
  readings: Reading[],
  windowMs: number = TREND_WINDOW_MS,
): TrendPoint[] {
  const history = readings.map(point).sort((a, b) => a.t - b.t);
  const lastHistory = history.at(-1)?.t ?? -Infinity;
  const newerLive = current.filter((p) => p.t > lastHistory + SAMPLE_SPACING_MS / 2);
  const merged = [...history, ...newerLive];
  const now = merged.at(-1)?.t ?? Date.now();
  return trim(merged, now, windowMs);
}

/** Add a live sample if at least a second has passed since the last point. */
export function appendLive(
  current: TrendPoint[],
  sample: Telemetry,
  windowMs: number = TREND_WINDOW_MS,
): TrendPoint[] {
  const next = point(sample);
  const last = current.at(-1);
  if (last && next.t - last.t < SAMPLE_SPACING_MS) return current;
  return trim([...current, next], next.t, windowMs);
}
