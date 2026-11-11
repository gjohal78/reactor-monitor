import { describe, expect, it, vi } from "vitest";

import { fetchHealth, type HealthResponse } from "./health";

const healthy: HealthResponse = {
  status: "ok",
  service: "reactor-monitor",
  version: "0.1.0",
  environment: "test",
};

function mockFetch(body: unknown, init: ResponseInit = { status: 200 }) {
  return vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(body), init));
}

describe("fetchHealth", () => {
  it("returns the parsed payload from /api/health", async () => {
    const fetchImpl = mockFetch(healthy);

    await expect(fetchHealth(fetchImpl)).resolves.toEqual(healthy);
    expect(fetchImpl).toHaveBeenCalledWith("/api/health", { signal: undefined });
  });

  it("throws on a non-2xx response", async () => {
    const fetchImpl = mockFetch({ detail: "nope" }, { status: 503 });

    await expect(fetchHealth(fetchImpl)).rejects.toThrow("HTTP 503");
  });

  it("throws when the payload has the wrong shape", async () => {
    const fetchImpl = mockFetch({ status: "degraded" });

    await expect(fetchHealth(fetchImpl)).rejects.toThrow("unexpected payload");
  });
});
