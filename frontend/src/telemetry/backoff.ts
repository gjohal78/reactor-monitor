/**
 * Reconnect delay: exponential backoff (0.5 s, 1 s, 2 s, 4 s, 8 s) capped at 10 s, with up
 * to 20 % random jitter so many clients don't all reconnect in the same instant after a
 * server restart.
 */
export const BASE_DELAY_MS = 500;
export const MAX_DELAY_MS = 10_000;

export function reconnectDelay(attempt: number, random: () => number = Math.random): number {
  const exponential = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** attempt);
  return Math.round(exponential * (1 + 0.2 * random()));
}
