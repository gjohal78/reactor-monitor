/**
 * HTTP client for the backend API.
 *
 * Tokens live in sessionStorage: they survive a page reload but not closing the tab, and
 * aren't shared between tabs. (An httpOnly cookie would keep them out of reach of
 * JavaScript entirely; that needs backend changes and is a sensible next step.)
 *
 * On a 401 the client refreshes the access token once and retries. Concurrent requests
 * share a single refresh. If the refresh fails, the session is cleared and listeners are
 * told, so the app can send the user back to the login page.
 */
import type { TokenPair } from "./types";

export const API_BASE = "/api";
const STORAGE_KEY = "reactor-monitor.tokens";

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface StoredTokens {
  access: string;
  refresh: string;
}

let tokens: StoredTokens | null = readStoredTokens();
let refreshInFlight: Promise<string> | null = null;
const sessionListeners = new Set<() => void>();

function readStoredTokens(): StoredTokens | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    return null;
  }
}

export function setTokens(pair: TokenPair): void {
  tokens = { access: pair.access_token, refresh: pair.refresh_token };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  } catch {
    // Storage unavailable (private mode etc.): keep the session in memory only.
  }
}

export function clearTokens(): void {
  tokens = null;
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

export function hasSession(): boolean {
  return tokens !== null;
}

/** Called when the session ends unexpectedly (refresh failed). Returns an unsubscribe. */
export function onSessionExpired(listener: () => void): () => void {
  sessionListeners.add(listener);
  return () => sessionListeners.delete(listener);
}

/** Seconds until a JWT expires (from its exp claim), or 0 if unreadable. */
export function secondsUntilExpiry(jwt: string, now: number = Date.now()): number {
  try {
    const payload = jwt.split(".")[1] ?? "";
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: number }).exp ?? 0;
    return exp - now / 1000;
  } catch {
    return 0;
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors: [{loc, msg, ...}]
      return body.detail.map((d: { msg?: string }) => d.msg ?? "Invalid input").join("; ");
    }
  } catch {
    // not JSON
  }
  return `Request failed (HTTP ${String(response.status)})`;
}

async function refreshAccessToken(fetchImpl: typeof fetch): Promise<string> {
  if (!tokens) throw new ApiError(401, "Not signed in");
  const refreshToken = tokens.refresh;
  refreshInFlight ??= (async () => {
    try {
      const response = await fetchImpl(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) throw new ApiError(401, "Session expired. Sign in again.");
      const pair = (await response.json()) as TokenPair;
      setTokens(pair);
      return pair.access_token;
    } catch (error) {
      clearTokens();
      sessionListeners.forEach((listener) => {
        listener();
      });
      throw error instanceof ApiError ? error : new ApiError(401, "Session expired.");
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/**
 * A valid access token for a WebSocket connection, refreshed first if it expires within
 * the next minute. (The WebSocket checks the token only at connect time.)
 */
export async function freshAccessToken(fetchImpl: typeof fetch = fetch): Promise<string> {
  if (!tokens) throw new ApiError(401, "Not signed in");
  if (secondsUntilExpiry(tokens.access) > 60) return tokens.access;
  return refreshAccessToken(fetchImpl);
}

export interface RequestOptions {
  method?: string;
  json?: unknown;
  form?: Record<string, string>;
  query?: Record<string, string | number | undefined>;
  auth?: boolean;
  fetchImpl?: typeof fetch;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", json, form, query, auth = true, fetchImpl = fetch } = options;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const url = `${API_BASE}${path}${params.size ? `?${params.toString()}` : ""}`;

  const send = (accessToken: string | undefined): Promise<Response> => {
    const headers: Record<string, string> = {};
    let body: string | undefined;
    if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(json);
    } else if (form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      body = new URLSearchParams(form).toString();
    }
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return fetchImpl(url, { method, headers, body });
  };

  let response = await send(auth ? tokens?.access : undefined);
  if (response.status === 401 && auth && tokens) {
    response = await send(await refreshAccessToken(fetchImpl));
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}
