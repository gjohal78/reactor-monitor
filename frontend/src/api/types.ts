// Mirrors backend/app/schemas.py. Keep the two in step.

export type Role = "viewer" | "operator" | "supervisor";

export interface User {
  id: number;
  username: string;
  role: Role;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface StateFields {
  sim_time_s: number;
  power_percent: number;
  coolant_temp_c: number;
  rod_position_percent: number;
  rod_target_percent: number;
  /** Seconds; null = effectively infinite (steady). Negative = power falling. */
  reactor_period_s: number | null;
  reactivity_pcm: number;
  scrammed: boolean;
}

export interface Telemetry extends StateFields {
  timestamp: string;
}

export interface Reading extends StateFields {
  id: number;
  timestamp: string;
}

export interface HistoryResponse {
  minutes: number;
  count: number;
  readings: Reading[];
}

export type AlarmState = "NORMAL" | "ACTIVE_UNACKED" | "ACTIVE_ACKED" | "CLEARED_UNACKED";

export interface Alarm {
  id: string;
  code: string;
  description: string;
  unit: string;
  state: AlarmState;
  limit: number;
  deadband: number;
  trigger_value: number;
  activation_count: number;
  activated_at: string;
  acknowledged_at: string | null;
  cleared_at: string | null;
  closed_at: string | null;
  updated_at: string | null;
}

export interface AlarmChange extends Alarm {
  previous_state: AlarmState;
  event: "CONDITION_ACTIVE" | "CONDITION_CLEAR" | "ACK";
}

export interface AlarmLimits {
  hi_power_percent: number;
  hi_power_deadband: number;
  hi_temp_c: number;
  hi_temp_deadband: number;
  short_period_s: number;
  short_period_deadband: number;
}

export interface RodEnvelope {
  min_insertion_percent: number;
  max_withdraw_step_percent: number;
}

export interface ReactorControl {
  rod_target_percent: number;
  rod_position_percent: number;
  scrammed: boolean;
}

export type AuditAction =
  | "LOGIN"
  | "ALARM_ACK"
  | "ROD_MOVE"
  | "SCRAM"
  | "SCRAM_RESET"
  | "ALARM_LIMITS_CHANGE"
  | "ACCESS_DENIED";

export interface AuditEntry {
  id: number;
  timestamp: string;
  user_id: number | null;
  username: string;
  role: Role | null;
  action: AuditAction;
  target: string | null;
  success: boolean;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  detail: string | null;
  client_ip: string | null;
}

export type ServerMessage =
  | { type: "alarm_snapshot"; data: Alarm[] }
  | { type: "telemetry"; data: Telemetry }
  | { type: "alarm"; data: AlarmChange };
