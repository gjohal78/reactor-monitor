import { afterEach, describe, expect, it, vi } from "vitest";

import { api, clearTokens, hasSession, onSessionExpired, setTokens } from "./client";

const pair = (n: number) => ({
  access_token: `access-${String(n)}`,
  refresh_token: `refresh-${String(n)}`,
  token_type: "bearer" as const,
  expires_in: 900,
});

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function authHeader(call: unknown[]): string | undefined {
  const init = call[1] as RequestInit | undefined;
  return (init?.headers as Record<string, string> | undefined)?.Authorization;
}

describe("api client", () => {
  afterEach(() => {
    clearTokens();
  });

  it("sends the access token", async () => {
    setTokens(pair(1));
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(json(200, { ok: true }));

    await api("/alarms", { fetchImpl });

    expect(authHeader(fetchImpl.mock.calls[0] ?? [])).toBe("Bearer access-1");
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    setTokens(pair(1));
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(401, { detail: "expired" }))
      .mockResolvedValueOnce(json(200, pair(2)))
      .mockResolvedValueOnce(json(200, { ok: true }));

    await expect(api("/alarms", { fetchImpl })).resolves.toEqual({ ok: true });

    expect(fetchImpl.mock.calls[1]?.[0]).toBe("/api/auth/refresh");
    expect(authHeader(fetchImpl.mock.calls[2] ?? [])).toBe("Bearer access-2");
  });

  it("ends the session when the refresh fails", async () => {
    setTokens(pair(1));
    const expired = vi.fn();
    const unsubscribe = onSessionExpired(expired);
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(401, { detail: "expired" }))
      .mockResolvedValueOnce(json(401, { detail: "refresh expired" }));

    await expect(api("/alarms", { fetchImpl })).rejects.toMatchObject({ status: 401 });

    expect(expired).toHaveBeenCalledOnce();
    expect(hasSession()).toBe(false);
    unsubscribe();
  });

  it("surfaces the server's error message", async () => {
    setTokens(pair(1));
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(json(422, { detail: "One command may withdraw rods at most 5.0 %" }));

    await expect(api("/reactor/rods", { method: "POST", fetchImpl })).rejects.toThrow(
      "One command may withdraw rods at most 5.0 %",
    );
  });

  it("does not try to refresh a 403", async () => {
    setTokens(pair(1));
    const fetchImpl = vi
      .fn<typeof fetch>()
      .mockResolvedValue(json(403, { detail: "Requires the supervisor role or higher" }));

    await expect(api("/audit", { fetchImpl })).rejects.toMatchObject({ status: 403 });
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});
