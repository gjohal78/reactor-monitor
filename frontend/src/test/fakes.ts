import type { Alarm, AlarmState, Telemetry } from "../api/types";

export function telemetry(overrides: Partial<Telemetry> = {}): Telemetry {
  return {
    timestamp: "2026-11-20T12:00:00Z",
    sim_time_s: 10,
    power_percent: 100,
    coolant_temp_c: 310,
    rod_position_percent: 20,
    rod_target_percent: 20,
    reactor_period_s: null,
    reactivity_pcm: 0,
    scrammed: false,
    ...overrides,
  };
}

export function alarm(state: AlarmState, overrides: Partial<Alarm> = {}): Alarm {
  return {
    id: "a1",
    code: "HI_POWER",
    description: "Reactor power high",
    unit: "%",
    state,
    limit: 105,
    deadband: 2,
    trigger_value: 110,
    activation_count: 1,
    activated_at: "2026-11-20T12:00:00Z",
    acknowledged_at: null,
    cleared_at: null,
    closed_at: null,
    updated_at: null,
    ...overrides,
  };
}

/** A controllable stand-in for the browser WebSocket. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  receive(message: unknown) {
    this.onmessage?.({ data: JSON.stringify(message) });
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  /** Server or network drops the connection. */
  drop() {
    this.close();
  }
}
