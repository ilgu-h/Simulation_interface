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

export type AnalyticalNetworkConfig = {
  kind: "analytical";
  topology: TopologyKind[];
  npus_count: number[];
  bandwidth: number[];
  latency: number[];
};

/**
 * ns-3 congestion control modes. Only 1/3/7/8/10 are implemented in
 * astra-sim's rdma-hw.cc; 11/12 appear in upstream docs + the shipped
 * default but have no code. Mirrors the backend `CCMode` literal.
 */
export type CCMode = 1 | 3 | 7 | 8 | 10 | 11 | 12;

export const CC_MODE_OPTIONS: ReadonlyArray<{ value: CCMode; label: string; experimental: boolean }> = [
  { value: 1, label: "DCQCN (1)", experimental: false },
  { value: 3, label: "HPCC (3)", experimental: false },
  { value: 7, label: "TIMELY (7)", experimental: false },
  { value: 8, label: "DCTCP (8)", experimental: false },
  { value: 10, label: "PINT (10)", experimental: false },
  { value: 11, label: "HPCC-PINT (11, experimental)", experimental: true },
  { value: 12, label: "HPCC-PINT-HAI (12, experimental)", experimental: true },
];

export type EcnThresholdEntry = { bandwidth_bps: number; threshold: number };
export type EcnProbabilityEntry = { bandwidth_bps: number; probability: number };
export type LinkDown = { src: number; dst: number; time: number };

export type Ns3NetworkConfig = {
  kind: "ns3";
  logical_dims: number[];
  physical_topology_path: string;
  mix_config_path: string;

  // Essentials
  cc_mode: CCMode;
  packet_payload_size: number;
  buffer_size: number;
  error_rate_per_link: number;
  enable_qcn: boolean;
  rate_ai: string;
  rate_hai: string;
  min_rate: string;

  // Congestion control tuning
  alpha_resume_interval: number;
  rate_decrease_interval: number;
  rp_timer: number;
  ewma_gain: number;
  fast_recovery_times: number;
  clamp_target_rate: boolean;

  // HPCC / window advanced
  has_win: boolean;
  global_t: number;
  var_win: boolean;
  fast_react: boolean;
  u_target: number;
  mi_thresh: number;
  int_multi: number;
  pint_log_base: number;
  pint_prob: number;
  multi_rate: boolean;
  sample_feedback: boolean;
  rate_bound: boolean;
  dctcp_rate_ai: string;

  // Global switches
  use_dynamic_pfc_threshold: boolean;
  enable_trace: boolean;
  ack_high_prio: boolean;
  l2_back_to_zero: boolean;

  // Packet / link layer
  l2_chunk_size: number;
  l2_ack_interval: number;
  nic_total_pause_time: number;

  // Timing (picoseconds)
  simulator_stop_time: number;
  qlen_mon_start: number;
  qlen_mon_end: number;

  // ECN threshold maps
  kmax_map: EcnThresholdEntry[];
  kmin_map: EcnThresholdEntry[];
  pmax_map: EcnProbabilityEntry[];

  // Link control
  link_down: LinkDown;

  // Escape hatch — keys not modeled above
  extra_overrides: Record<string, string>;
};

export type NetworkConfig = AnalyticalNetworkConfig | Ns3NetworkConfig;

export const isNs3NetworkConfig = (n: NetworkConfig): n is Ns3NetworkConfig =>
  n.kind === "ns3";

export const isAnalyticalNetworkConfig = (
  n: NetworkConfig,
): n is AnalyticalNetworkConfig => n.kind === "analytical";

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

export const defaultNetworkConfig = (): AnalyticalNetworkConfig => ({
  kind: "analytical",
  topology: ["Ring"],
  npus_count: [8],
  bandwidth: [50.0],
  latency: [500.0],
});

const NS3_ECN_DEFAULT_BANDWIDTHS: ReadonlyArray<number> = [
  25_000_000_000, 40_000_000_000, 100_000_000_000,
  200_000_000_000, 400_000_000_000, 2_400_000_000_000,
];
const NS3_KMAX_DEFAULTS: ReadonlyArray<number> = [400, 800, 1600, 2400, 3200, 3200];
const NS3_KMIN_DEFAULTS: ReadonlyArray<number> = [100, 200, 400, 600, 800, 800];

export const defaultNs3NetworkConfig = (): Ns3NetworkConfig => ({
  kind: "ns3",
  logical_dims: [8],
  physical_topology_path:
    "extern/network_backend/ns-3/scratch/topology/8_nodes_1_switch_topology.txt",
  mix_config_path: "extern/network_backend/ns-3/scratch/config/config.txt",

  // Essentials
  cc_mode: 12,
  packet_payload_size: 1000,
  buffer_size: 32,
  error_rate_per_link: 0.0,
  enable_qcn: true,
  rate_ai: "50Mb/s",
  rate_hai: "100Mb/s",
  min_rate: "100Mb/s",

  // Congestion control tuning
  alpha_resume_interval: 1,
  rate_decrease_interval: 4,
  rp_timer: 900,
  ewma_gain: 0.00390625,
  fast_recovery_times: 1,
  clamp_target_rate: false,

  // HPCC / window advanced
  has_win: true,
  global_t: 0,
  var_win: true,
  fast_react: true,
  u_target: 0.95,
  mi_thresh: 0,
  int_multi: 1,
  pint_log_base: 1.05,
  pint_prob: 1.0,
  multi_rate: false,
  sample_feedback: false,
  rate_bound: true,
  dctcp_rate_ai: "1000Mb/s",

  // Global switches
  use_dynamic_pfc_threshold: true,
  enable_trace: true,
  ack_high_prio: false,
  l2_back_to_zero: false,

  // Packet / link layer
  l2_chunk_size: 4000,
  l2_ack_interval: 1,
  nic_total_pause_time: 0,

  // Timing (picoseconds)
  simulator_stop_time: 4e13,
  qlen_mon_start: 0,
  qlen_mon_end: 20000,

  // ECN threshold maps — match backend defaults per NIC bandwidth
  kmax_map: NS3_ECN_DEFAULT_BANDWIDTHS.map((bandwidth_bps, i) => ({
    bandwidth_bps, threshold: NS3_KMAX_DEFAULTS[i],
  })),
  kmin_map: NS3_ECN_DEFAULT_BANDWIDTHS.map((bandwidth_bps, i) => ({
    bandwidth_bps, threshold: NS3_KMIN_DEFAULTS[i],
  })),
  pmax_map: NS3_ECN_DEFAULT_BANDWIDTHS.map((bandwidth_bps) => ({
    bandwidth_bps, probability: 0.2,
  })),

  link_down: { src: 0, dst: 0, time: 0 },
  extra_overrides: {},
});

/**
 * Total NPU count for whichever variant `n` is.
 * Analytical: prod(npus_count). NS3: prod(logical_dims).
 */
export const networkTotalNpus = (n: NetworkConfig): number => {
  const dims = isNs3NetworkConfig(n) ? n.logical_dims : n.npus_count;
  return dims.reduce((a, b) => a * b, 1);
};

/** Pick the right default for a given network_schema string from /backends. */
export const defaultNetworkForSchema = (
  schema: string | undefined,
): NetworkConfig =>
  schema === "ns3" ? defaultNs3NetworkConfig() : defaultNetworkConfig();

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
