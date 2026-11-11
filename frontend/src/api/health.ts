export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}

export const API_BASE = "/api";

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    v.status === "ok" &&
    typeof v.service === "string" &&
    typeof v.version === "string" &&
    typeof v.environment === "string"
  );
}

/** Calls the backend liveness endpoint. Throws on network, HTTP or shape errors. */
export async function fetchHealth(
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetchImpl(`${API_BASE}/health`, { signal });
  if (!response.ok) {
    throw new Error(`Health check failed: HTTP ${String(response.status)}`);
  }
  const body: unknown = await response.json();
  if (!isHealthResponse(body)) {
    throw new Error("Health check returned an unexpected payload");
  }
  return body;
}
