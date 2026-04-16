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

export type BackendInfo = {
  name: string;
  label: string;
  network_schema: string;
  binary_path: string;
  built: boolean;
};

export const listBackends = (): Promise<BackendInfo[]> => getJson<BackendInfo[]>("/backends");

export type TopologyKind = "Ring" | "FullyConnected" | "Switch";

export type NetworkConfig = {
  topology: TopologyKind[];
  npus_count: number[];
  bandwidth: number[];
  latency: number[];
};

export type SystemConfig = {
  "scheduling-policy": "LIFO" | "FIFO";
  "endpoint-delay": number;
  "active-chunks-per-dimension": number;
  "preferred-dataset-splits": number;
  "all-reduce-implementation": string[];
  "all-gather-implementation": string[];
  "reduce-scatter-implementation": string[];
  "all-to-all-implementation": string[];
  "collective-optimization": "localBWAware" | "";
  "local-mem-bw": number;
  "boost-mode": 0 | 1;
  "roofline-enabled"?: 0 | 1;
  "peak-perf"?: number;
};

export type MemoryType =
  | "NO_MEMORY_EXPANSION"
  | "PER_NODE_MEMORY_EXPANSION"
  | "PER_NPU_MEMORY_EXPANSION"
  | "MEMORY_POOL";

export type MemoryConfig = {
  "memory-type": MemoryType;
  "remote-mem-latency": number;
  "remote-mem-bw": number;
  "num-nodes"?: number | null;
  "num-npus-per-node"?: number | null;
};

export type ConfigBundle = {
  backend: string;
  system: SystemConfig;
  network: NetworkConfig;
  memory: MemoryConfig;
  expected_npus?: number | null;
};

export type Issue = {
  severity: "error" | "warning" | "info";
  field: string;
  message: string;
};

export type ValidateResponse = {
  ok: boolean;
  issues: Issue[];
  total_npus: number;
  binary_present: boolean;
};

export type MaterializeResponse = {
  run_id: string;
  config_dir: string;
  files: { network: string; system: string; memory: string };
};

export const validateConfigs = (b: ConfigBundle): Promise<ValidateResponse> =>
  postJson<ValidateResponse>("/configs/validate", b);

export const materializeConfigs = (b: ConfigBundle): Promise<MaterializeResponse> =>
  postJson<MaterializeResponse>("/configs/materialize", b);

export type WorkloadRef = {
  kind: "existing" | "run";
  value: string;
  name?: string;
};

export type RunValidateRequest = {
  workload: WorkloadRef;
  bundle: ConfigBundle;
  smoke_run?: boolean;
};

export type WorkloadSummary = {
  prefix: string;
  trace_count: number;
  total_size_bytes: number;
};

export type SmokeRunResult = {
  ran: boolean;
  returncode: number | null;
  stdout_tail: string;
  stderr_tail: string;
  duration_sec: number | null;
};

export type RunValidateResponse = {
  ok: boolean;
  issues: Issue[];
  workload: WorkloadSummary | null;
  binary_present: boolean;
  smoke: SmokeRunResult | null;
  estimated_run_seconds: number | null;
};

export const validateRun = (req: RunValidateRequest): Promise<RunValidateResponse> =>
  postJson<RunValidateResponse>("/runs/validate", req);

export type StartRunRequest = { workload: WorkloadRef; bundle: ConfigBundle };

export type StartRunResponse = { run_id: string; status: string };

export const startRun = (req: StartRunRequest): Promise<StartRunResponse> =>
  postJson<StartRunResponse>("/runs", req);

export type RunListItem = {
  run_id: string;
  status: RunStatusValue;
  created_at: string;
};

export const listRuns = (): Promise<RunListItem[]> => getJson<RunListItem[]>("/runs");

export type RunStatusValue =
  | "queued"
  | "building"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type RunStatus = {
  run_id: string;
  status: RunStatusValue;
  config_dir: string | null;
  log_dir: string | null;
};

export const getRun = (run_id: string): Promise<RunStatus> =>
  getJson<RunStatus>(`/runs/${run_id}`);

export const cancelRun = (run_id: string): Promise<{ signalled: boolean }> =>
  postJson(`/runs/${run_id}/cancel`, {});

export const eventsUrl = (run_id: string): string =>
  `${backendUrl()}/runs/${run_id}/events`;

// ---------- Phase 5 results --------------------------------------------------

export type CollectiveAgg = {
  comm_type: string;
  count: number;
  total_bytes: number;
};

export type RunSummary = {
  run_id: string;
  npu_count: number;
  end_to_end_cycles: number;
  slowest_npu: number | null;
  avg_comm_fraction: number;
  top_collectives: CollectiveAgg[];
};

export const getSummary = (run_id: string): Promise<RunSummary> =>
  getJson<RunSummary>(`/results/${run_id}/summary`);

export type PerNpuRow = {
  npu_id: number;
  wall_cycles: number;
  comm_cycles: number;
  compute_cycles: number;
  exposed_comm_cycles: number;
  comm_fraction: number;
};

export type PerCollectiveRow = {
  npu_id: number;
  node_id: number;
  name: string;
  comm_type: string;
  comm_size_bytes: number;
};

export const getStats = <T = unknown>(
  run_id: string,
  view: "per_npu" | "per_collective" | "per_collective_agg",
): Promise<T[]> => getJson<T[]>(`/results/${run_id}/stats?view=${view}`);

export const timelineUrl = (run_id: string): string =>
  `${backendUrl()}/results/${run_id}/timeline.json`;

export const logUrl = (run_id: string, name: string): string =>
  `${backendUrl()}/results/${run_id}/logs/${name}`;

export type FieldDiff = { path: string; a: unknown; b: unknown };

export type CompareResult = {
  a: string;
  b: string;
  summary_a: RunSummary;
  summary_b: RunSummary;
  e2e_delta_cycles: number;
  e2e_delta_pct: number;
  config_diffs: FieldDiff[];
};

export const compareRuns = (a: string, b: string): Promise<CompareResult> =>
  getJson<CompareResult>(`/results/${a}/compare?with=${b}`);

export const defaultSystemConfig = (): SystemConfig => ({
  "scheduling-policy": "LIFO",
  "endpoint-delay": 10,
  "active-chunks-per-dimension": 1,
  "preferred-dataset-splits": 4,
  "all-reduce-implementation": ["ring"],
  "all-gather-implementation": ["ring"],
  "reduce-scatter-implementation": ["ring"],
  "all-to-all-implementation": ["ring"],
  "collective-optimization": "localBWAware",
  "local-mem-bw": 1600,
  "boost-mode": 0,
});

export const defaultNetworkConfig = (): NetworkConfig => ({
  topology: ["Ring"],
  npus_count: [8],
  bandwidth: [50.0],
  latency: [500.0],
});

export const defaultMemoryConfig = (): MemoryConfig => ({
  "memory-type": "NO_MEMORY_EXPANSION",
  "remote-mem-latency": 0,
  "remote-mem-bw": 0,
  "num-nodes": null,
  "num-npus-per-node": null,
});

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
