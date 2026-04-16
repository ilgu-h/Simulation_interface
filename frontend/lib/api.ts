/**
 * Backend API client. Phase 0 only knows about /health.
 * Endpoint base is configurable via NEXT_PUBLIC_BACKEND_URL.
 */

const DEFAULT_BACKEND = "http://localhost:8000";

export const backendUrl = (): string =>
  process.env.NEXT_PUBLIC_BACKEND_URL ?? DEFAULT_BACKEND;

export type HealthResponse = { status: string };

export async function healthCheck(): Promise<HealthResponse> {
  const res = await fetch(`${backendUrl()}/health`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}
