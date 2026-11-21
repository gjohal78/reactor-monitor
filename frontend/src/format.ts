import type { AlarmState } from "./api/types";

export const formatPercent = (value: number, digits = 1) => `${value.toFixed(digits)} %`;
export const formatTemp = (value: number) => `${value.toFixed(1)} °C`;

export function formatPeriod(seconds: number | null): string {
  if (seconds === null) return "Steady";
  const sign = seconds < 0 ? "−" : "";
  return `${sign}${Math.abs(seconds).toFixed(Math.abs(seconds) < 100 ? 1 : 0)} s`;
}

export const formatClock = (iso: string | number) =>
  new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const formatDateTime = (iso: string) =>
  new Date(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

export const ALARM_STATE_LABEL: Record<AlarmState, string> = {
  ACTIVE_UNACKED: "Unacknowledged",
  ACTIVE_ACKED: "Acknowledged",
  CLEARED_UNACKED: "Cleared, not acknowledged",
  NORMAL: "Normal",
};

export type Severity = "unacked" | "acked" | "cleared" | "normal";

export function severity(state: AlarmState): Severity {
  switch (state) {
    case "ACTIVE_UNACKED":
      return "unacked";
    case "ACTIVE_ACKED":
      return "acked";
    case "CLEARED_UNACKED":
      return "cleared";
    case "NORMAL":
      return "normal";
  }
}

export function formatAlarmValue(value: number, unit: string): string {
  return unit === "%" ? formatPercent(value) : `${value.toFixed(1)} ${unit}`;
}
