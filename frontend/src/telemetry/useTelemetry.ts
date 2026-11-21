/**
 * Live connection to /ws/telemetry, with automatic reconnect.
 *
 * - Reconnects with exponential backoff (see backoff.ts) whenever the socket closes.
 * - A watchdog closes the socket if nothing arrives for 5 s (telemetry is 10 Hz, so
 *   silence means the connection is dead even if the browser hasn't noticed yet).
 * - The access token is refreshed before each connect: the server checks it only at
 *   connect time and rejects expired ones.
 * - Every (re)connect reloads the last 15 minutes of history, so the trend charts have
 *   no gap where the connection was down.
 */
import { useEffect, useReducer, useRef } from "react";

import { ApiError, freshAccessToken } from "../api/client";
import { getHistory } from "../api/endpoints";
import type { Alarm, Reading, ServerMessage, Telemetry } from "../api/types";
import { reconnectDelay } from "./backoff";
import { appendLive, mergeHistory, TREND_WINDOW_MS } from "./trend";
import type { TrendPoint } from "./trend";

export type ConnectionStatus = "connecting" | "live" | "reconnecting";

export interface TelemetryState {
  status: ConnectionStatus;
  telemetry: Telemetry | null;
  alarms: Alarm[];
  trend: TrendPoint[];
  /** When the next reconnect attempt happens (epoch ms), while reconnecting. */
  retryAt: number | null;
}

type Action =
  | { type: "status"; status: ConnectionStatus; retryAt?: number | null }
  | { type: "message"; message: ServerMessage }
  | { type: "history"; readings: Reading[] };

export const initialTelemetryState: TelemetryState = {
  status: "connecting",
  telemetry: null,
  alarms: [],
  trend: [],
  retryAt: null,
};

function sortAlarms(alarms: Alarm[]): Alarm[] {
  return [...alarms].sort((a, b) => a.activated_at.localeCompare(b.activated_at));
}

export function telemetryReducer(state: TelemetryState, action: Action): TelemetryState {
  switch (action.type) {
    case "status":
      return { ...state, status: action.status, retryAt: action.retryAt ?? null };
    case "history":
      return { ...state, trend: mergeHistory(state.trend, action.readings) };
    case "message": {
      const { message } = action;
      switch (message.type) {
        case "telemetry":
          return {
            ...state,
            telemetry: message.data,
            trend: appendLive(state.trend, message.data),
          };
        case "alarm_snapshot":
          return { ...state, alarms: sortAlarms(message.data) };
        case "alarm": {
          const others = state.alarms.filter((a) => a.id !== message.data.id);
          // NORMAL means the occurrence is closed: drop it from the open list.
          const alarms = message.data.state === "NORMAL" ? others : [...others, message.data];
          return { ...state, alarms: sortAlarms(alarms) };
        }
      }
    }
  }
}

export const STALE_AFTER_MS = 5000;
const OPEN = 1; // WebSocket.OPEN, without depending on the global (tests inject a fake)

export interface TelemetryOptions {
  /** Injected in tests. */
  WebSocketImpl?: typeof WebSocket;
  loadHistory?: (minutes: number) => Promise<{ readings: Reading[] }>;
  getToken?: () => Promise<string>;
  url?: (token: string) => string;
}

function defaultUrl(token: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/telemetry?token=${encodeURIComponent(token)}`;
}

export function useTelemetry(enabled: boolean, options: TelemetryOptions = {}): TelemetryState {
  const [state, dispatch] = useReducer(telemetryReducer, initialTelemetryState);
  const optionsRef = useRef(options);

  useEffect(() => {
    if (!enabled) return;
    const {
      WebSocketImpl = WebSocket,
      loadHistory = getHistory,
      getToken = freshAccessToken,
      url = defaultUrl,
    } = optionsRef.current;

    let socket: WebSocket | null = null;
    // Set from the cleanup function, possibly while connect() is awaiting. Read through a
    // function so TypeScript doesn't assume it can't have changed across an await.
    const life = { disposed: false };
    const isDisposed = (): boolean => life.disposed;
    let attempt = 0;
    let lastMessageAt = Date.now();
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const scheduleReconnect = () => {
      if (isDisposed()) return;
      const delay = reconnectDelay(attempt);
      attempt += 1;
      dispatch({ type: "status", status: "reconnecting", retryAt: Date.now() + delay });
      retryTimer = setTimeout(() => void connect(), delay);
    };

    const connect = async () => {
      if (isDisposed()) return;
      let token: string;
      try {
        token = await getToken();
      } catch (error) {
        // Refresh failed: the auth layer signs the user out. Retry only for other errors.
        if (!(error instanceof ApiError && error.status === 401)) scheduleReconnect();
        return;
      }
      if (isDisposed()) return;

      const ws = new WebSocketImpl(url(token));
      socket = ws;
      ws.onopen = () => {
        attempt = 0;
        lastMessageAt = Date.now();
        dispatch({ type: "status", status: "live" });
        const minutes = TREND_WINDOW_MS / 60_000;
        loadHistory(minutes)
          .then((history) => {
            if (!isDisposed()) dispatch({ type: "history", readings: history.readings });
          })
          .catch(() => {
            // Trends still fill from live data; history is a nice-to-have.
          });
      };
      ws.onmessage = (event: MessageEvent<string>) => {
        lastMessageAt = Date.now();
        try {
          dispatch({ type: "message", message: JSON.parse(event.data) as ServerMessage });
        } catch {
          // Ignore malformed frames rather than dropping the connection.
        }
      };
      ws.onclose = () => {
        if (socket === ws) socket = null;
        scheduleReconnect();
      };
    };

    const watchdog = setInterval(() => {
      if (socket?.readyState === OPEN && Date.now() - lastMessageAt > STALE_AFTER_MS) {
        socket.close(); // onclose schedules the reconnect
      }
    }, 1000);

    void connect();
    return () => {
      life.disposed = true;
      clearTimeout(retryTimer);
      clearInterval(watchdog);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, [enabled]);

  return state;
}
