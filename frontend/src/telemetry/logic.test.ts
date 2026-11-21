import { describe, expect, it } from "vitest";

import type { Reading } from "../api/types";
import { roleAllows } from "../auth/roles";
import { alarm, telemetry } from "../test/fakes";
import { BASE_DELAY_MS, MAX_DELAY_MS, reconnectDelay } from "./backoff";
import { appendLive, mergeHistory } from "./trend";
import { initialTelemetryState, telemetryReducer } from "./useTelemetry";

describe("roleAllows", () => {
  it.each([
    ["viewer", "viewer", true],
    ["viewer", "operator", false],
    ["operator", "operator", true],
    ["operator", "supervisor", false],
    ["supervisor", "operator", true],
    ["supervisor", "supervisor", true],
  ] as const)("%s needing %s -> %s", (role, required, expected) => {
    expect(roleAllows(role, required)).toBe(expected);
  });
});

describe("reconnectDelay", () => {
  it("doubles each attempt and caps at 10 s", () => {
    const noJitter = () => 0;
    expect([0, 1, 2, 3, 4, 5, 10].map((n) => reconnectDelay(n, noJitter))).toEqual([
      BASE_DELAY_MS,
      1000,
      2000,
      4000,
      8000,
      MAX_DELAY_MS,
      MAX_DELAY_MS,
    ]);
  });

  it("adds at most 20 % jitter", () => {
    expect(reconnectDelay(3, () => 0.999)).toBeLessThanOrEqual(4000 * 1.2);
    expect(reconnectDelay(3, () => 0.5)).toBe(4400);
  });
});

const at = (s: number) => new Date(Date.UTC(2026, 10, 20, 12, 0, s)).toISOString();

describe("trend buffer", () => {
  it("keeps one live sample per second", () => {
    let points = appendLive([], telemetry({ timestamp: at(0) }));
    points = appendLive(points, telemetry({ timestamp: at(0.4) }));
    points = appendLive(points, telemetry({ timestamp: at(1), power_percent: 101 }));

    expect(points.map((p) => p.power)).toEqual([100, 101]);
  });

  it("drops points older than the window", () => {
    let points = appendLive([], telemetry({ timestamp: at(0) }), 5000);
    points = appendLive(points, telemetry({ timestamp: at(3) }), 5000);
    points = appendLive(points, telemetry({ timestamp: at(7) }), 5000);

    expect(points.map((p) => p.t)).toEqual([Date.parse(at(3)), Date.parse(at(7))]);
  });

  it("history fills the gap but keeps newer live points", () => {
    const live = [appendLive([], telemetry({ timestamp: at(30), power_percent: 120 }))[0]].filter(
      (p) => p !== undefined,
    );
    const readings = [0, 1, 2].map(
      (s): Reading => ({ ...telemetry({ timestamp: at(s * 10), power_percent: 100 + s }), id: s }),
    );

    const merged = mergeHistory(live, readings);

    expect(merged.map((p) => p.power)).toEqual([100, 101, 102, 120]);
  });
});

describe("telemetryReducer alarms", () => {
  it("snapshot replaces, changes update, NORMAL removes", () => {
    let state = telemetryReducer(initialTelemetryState, {
      type: "message",
      message: { type: "alarm_snapshot", data: [alarm("ACTIVE_UNACKED")] },
    });
    expect(state.alarms.map((a) => a.state)).toEqual(["ACTIVE_UNACKED"]);

    state = telemetryReducer(state, {
      type: "message",
      message: {
        type: "alarm",
        data: { ...alarm("ACTIVE_ACKED"), previous_state: "ACTIVE_UNACKED", event: "ACK" },
      },
    });
    expect(state.alarms.map((a) => a.state)).toEqual(["ACTIVE_ACKED"]);

    state = telemetryReducer(state, {
      type: "message",
      message: {
        type: "alarm",
        data: { ...alarm("NORMAL"), previous_state: "ACTIVE_ACKED", event: "CONDITION_CLEAR" },
      },
    });
    expect(state.alarms).toEqual([]);
  });
});
