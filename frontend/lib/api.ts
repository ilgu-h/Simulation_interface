/**
 * Backend API client. Phase 0 only knows about /health.
 * Endpoint base is configurable via NEXT_PUBLIC_BACKEND_URL.
 */

const DEFAULT_BACKEND = "http://localhost:8000";

export const backendUrl = (): string =>
  process.env.NEXT_PUBLIC_BACKEND_URL ?? DEFAULT_BACKEND;

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${backendUrl()}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status} on ${path}`);
  return res.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${backendUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} on ${path}: ${detail.slice(0, 500)}`);
  }
  return res.json();
}

export type HealthResponse = { status: string };

export const healthCheck = (): Promise<HealthResponse> => getJson<HealthResponse>("/health");

export type LibraryEntry = {
  source: "examples" | "run";
  run_id: string | null;
  name: string;
  path: string;
  size_bytes: number;
};

export const listWorkloadLibrary = (): Promise<LibraryEntry[]> =>
  getJson<LibraryEntry[]>("/workloads/library");

export type Preset = {
  id: string;
  label: string;
  model_type: string;
  spec: Record<string, unknown>;
};

export const listPresets = (): Promise<Preset[]> => getJson<Preset[]>("/workloads/presets");

export type StgSpec = {
  model_type: "llama" | "dense" | "gpt" | "moe" | "debug";
  dp: number;
  tp: number;
  sp: number;
  pp: number;
  ep: number;
  dvocal: number;
  dmodel: number;
  dff: number;
  head: number;
  kvhead: number;
  num_stacks: number;
  experts: number;
  kexperts: number;
  batch: number;
  micro_batch: number;
  seq: number;
  weight_sharded: boolean;
  activation_recompute: boolean;
  tpsp: boolean;
  mixed_precision: boolean;
  chakra_schema_version: string;
};

export type GenerateResponse = {
  run_id: string;
  total_npus: number;
  trace_files: string[];
  stdout_tail: string;
};

export const generateWorkload = (spec: StgSpec): Promise<GenerateResponse> =>
  postJson<GenerateResponse>("/workloads/generate", spec);

export const defaultStgSpec = (): StgSpec => ({
  model_type: "dense",
  dp: 1,
  tp: 1,
  sp: 1,
  pp: 1,
  ep: 1,
  dvocal: 32000,
  dmodel: 8192,
  dff: 28672,
  head: 64,
  kvhead: 8,
  num_stacks: 80,
  experts: 8,
  kexperts: 2,
  batch: 64,
  micro_batch: -1,
  seq: 1024,
  weight_sharded: false,
  activation_recompute: false,
  tpsp: true,
  mixed_precision: false,
  chakra_schema_version: "v0.0.4",
});
