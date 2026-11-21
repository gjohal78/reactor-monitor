const NICE_STEPS = [0.5, 1, 2, 5, 10, 20, 25, 50, 100];

/** Evenly spaced round-number ticks covering [low, high], about five of them. */
export function niceTicks(low: number, high: number, target = 5): number[] {
  const raw = (high - low) / target;
  const step = NICE_STEPS.find((s) => s >= raw) ?? NICE_STEPS[NICE_STEPS.length - 1] ?? 100;
  const start = Math.floor(low / step) * step;
  const end = Math.ceil(high / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 1000; v += step) ticks.push(Math.round(v * 1000) / 1000);
  return ticks;
}
