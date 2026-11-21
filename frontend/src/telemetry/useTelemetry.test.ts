import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeWebSocket, telemetry } from "../test/fakes";
import { STALE_AFTER_MS, useTelemetry } from "./useTelemetry";

function setup() {
  const getToken = vi.fn(() => Promise.resolve("token-1"));
  const loadHistory = vi.fn(() => Promise.resolve({ readings: [] }));
  const hook = renderHook(() =>
    useTelemetry(true, {
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      getToken,
      loadHistory,
      url: (token) => `ws://test/ws/telemetry?token=${token}`,
    }),
  );
  return { ...hook, getToken, loadHistory };
}

const latest = () => {
  const socket = FakeWebSocket.instances.at(-1);
  if (!socket) throw new Error("no socket yet");
  return socket;
};

describe("useTelemetry", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.instances = [];
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("connects with a token, goes live and loads history", async () => {
    const { result, loadHistory } = setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(latest().url).toBe("ws://test/ws/telemetry?token=token-1");

    act(() => {
      latest().open();
      latest().receive({ type: "telemetry", data: telemetry({ power_percent: 101 }) });
    });

    expect(result.current.status).toBe("live");
    expect(result.current.telemetry?.power_percent).toBe(101);
    expect(loadHistory).toHaveBeenCalledWith(15);
  });

  it("reconnects with backoff after the connection drops, refreshing the token", async () => {
    const { result, getToken } = setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      latest().open();
    });

    act(() => {
      latest().drop();
    });
    expect(result.current.status).toBe("reconnecting");
    expect(result.current.retryAt).not.toBeNull();
    expect(FakeWebSocket.instances).toHaveLength(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(700); // first retry: 500-600 ms
    });
    expect(FakeWebSocket.instances).toHaveLength(2);
    expect(getToken).toHaveBeenCalledTimes(2); // a fresh token for every connect

    act(() => {
      latest().open();
    });
    expect(result.current.status).toBe("live");
  });

  it("keeps retrying, waiting longer each time", async () => {
    setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    for (const wait of [700, 1300, 2500]) {
      act(() => {
        latest().drop();
      });
      const before = FakeWebSocket.instances.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(wait * 0.7);
      });
      expect(FakeWebSocket.instances).toHaveLength(before); // not yet
      await act(async () => {
        await vi.advanceTimersByTimeAsync(wait * 0.5);
      });
      expect(FakeWebSocket.instances).toHaveLength(before + 1);
    }
  });

  it("treats a silent connection as dead and reconnects", async () => {
    const { result } = setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      latest().open();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(STALE_AFTER_MS + 1500);
    });

    expect(result.current.status).toBe("reconnecting");
  });

  it("closes the socket and stops reconnecting on unmount", async () => {
    const { unmount } = setup();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => {
      latest().open();
    });

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });

    expect(latest().readyState).toBe(3);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
