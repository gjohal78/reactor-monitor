import { api } from "./client";
import type {
  Alarm,
  AlarmLimits,
  AuditAction,
  AuditEntry,
  HistoryResponse,
  ReactorControl,
  RodEnvelope,
  TokenPair,
  User,
} from "./types";

export const login = (username: string, password: string) =>
  api<TokenPair>("/auth/login", { method: "POST", form: { username, password }, auth: false });

export const getMe = () => api<User>("/auth/me");

export const getHistory = (minutes: number) =>
  api<HistoryResponse>("/history", { query: { minutes } });

export const getAlarmLimits = () => api<AlarmLimits>("/alarms/limits");

export const ackAlarm = (id: string) => api<Alarm>(`/alarms/${id}/ack`, { method: "POST" });

export const getRodEnvelope = () => api<RodEnvelope>("/reactor/envelope");

export const moveRods = (targetPercent: number) =>
  api<ReactorControl>("/reactor/rods", { method: "POST", json: { target_percent: targetPercent } });

export const scram = () => api<ReactorControl>("/reactor/scram", { method: "POST" });

export const resetScram = () => api<ReactorControl>("/reactor/reset-scram", { method: "POST" });

export interface AuditQuery {
  limit: number;
  offset: number;
  action?: AuditAction;
  username?: string;
}

export const getAudit = (query: AuditQuery) =>
  api<AuditEntry[]>("/audit", { query: { ...query } });
