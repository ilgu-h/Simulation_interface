# Simulation Interface — Developer Manual

> Technical reference for developers extending, debugging, and maintaining the Simulation Interface.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Frontend Architecture](#2-frontend-architecture)
3. [Backend Architecture](#3-backend-architecture)
4. [API Reference](#4-api-reference)
5. [Custom Workload Generation](#5-custom-workload-generation)
6. [Custom System Configuration](#6-custom-system-configuration)
7. [Extending the System](#7-extending-the-system)
8. [Testing Guide](#8-testing-guide)
9. [Debugging Guide](#9-debugging-guide)

---

## 1. Architecture Overview

### 1.1 Pipeline Diagram

```
┌──────────┐     ┌──────────────┐     ┌──────────────────────────────────┐
│  Browser  │────▶│  Next.js 14  │────▶│        FastAPI Backend           │
│ :3000     │◀────│  (frontend/) │◀────│        (backend/)                │
└──────────┘     └──────────────┘     │                                  │
                                      │  ┌────────────┐  ┌────────────┐  │
                                      │  │    STG      │  │   Chakra   │  │
                                      │  │  (conda)    │  │   (pip)    │  │
                                      │  └─────┬──────┘  └─────┬──────┘  │
                                      │        │  .et files     │ validate│
                                      │        ▼               ▼         │
                                      │  ┌─────────────────────────────┐ │
                                      │  │     ASTRA-sim (C++ binary)  │ │
                                      │  └──────────────┬──────────────┘ │
                                      │                 │                │
                                      └─────────────────┼────────────────┘
                                                        ▼
                                                  runs/<id>/
                                                  ├── configs/
                                                  ├── traces/
                                                  ├── logs/
                                                  └── spec.json
```

### 1.2 Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js (App Router) | 14.2.15 |
| Frontend | React | 18.3.1 |
| Frontend | TypeScript (strict) | 5.6.2 |
| Frontend | Tailwind CSS | 3.4.13 |
| Backend | FastAPI | 0.115+ |
| Backend | Python | 3.11+ |
| Backend | Pydantic v2 | 2.7+ |
| Backend | SQLModel (SQLite) | 0.0.22+ |
| Backend | pandas + pyarrow | 2.2+ / 17.0+ |
| Simulation | ASTRA-sim | Git submodule |
| Traces | Chakra (MLCommons) | Git submodule (editable pip) |
| Workload Gen | STG | Git submodule (conda env) |

### 1.3 Repository Layout

```
Simulation_interface/
├── backend/                     # FastAPI application
│   ├── app/
│   │   ├── main.py              # App factory, CORS, router mounting (54 lines)
│   │   ├── api/                 # Route handlers
│   │   │   ├── workload.py      # /workloads/* endpoints (152 lines)
│   │   │   ├── system.py        # /configs/*, /backends endpoints (181 lines)
│   │   │   ├── runs.py          # /runs/* endpoints (435 lines)
│   │   │   └── results.py       # /results/* endpoints (362 lines)
│   │   ├── schemas/             # Pydantic models
│   │   │   ├── stg_spec.py      # STG workload specification (83 lines)
│   │   │   ├── network_config.py # Network topology model (84 lines)
│   │   │   ├── system_config.py # System parameters model (64 lines)
│   │   │   ├── memory_config.py # Memory config model (22 lines)
│   │   │   └── presets/         # JSON preset files
│   │   │       ├── llama-7b.json
│   │   │       ├── llama-70b.json
│   │   │       └── gpt3-175b.json
│   │   ├── orchestrator/        # Subprocess management
│   │   │   ├── pipeline.py      # Run state machine + event logging (226 lines)
│   │   │   ├── astra_runner.py  # ASTRA-sim process wrapper (123 lines)
│   │   │   ├── stg_runner.py    # STG conda subprocess (97 lines)
│   │   │   └── chakra_tools.py  # Chakra visualization wrapper (74 lines)
│   │   ├── parsers/             # Output parsing
│   │   │   ├── astra_logs.py    # Regex log → NpuStats (109 lines)
│   │   │   └── et_traces.py     # Protobuf .et → CollectiveOp (127 lines)
│   │   ├── build/               # Backend registry
│   │   │   └── backend_adapter.py # BackendAdapter dataclass + registry (76 lines)
│   │   └── storage/             # Persistence
│   │       ├── registry.py      # SQLModel tables + engine (56 lines)
│   │       └── fs_layout.py     # Path construction helpers (33 lines)
│   ├── tests/                   # Test suite (56 tests, 81%+ coverage)
│   │   ├── conftest.py          # Fixtures: app, client
│   │   ├── unit/                # Pure function tests
│   │   ├── integration/         # API endpoint tests
│   │   └── smoke/               # Full binary tests
│   ├── conftest.py              # Root: SIM_RUNS_DIR isolation
│   └── pyproject.toml           # Dependencies + tool config
├── frontend/                    # Next.js application
│   ├── app/                     # Pages (App Router)
│   │   ├── layout.tsx           # Root layout + navigation (41 lines)
│   │   ├── page.tsx             # Dashboard (112 lines)
│   │   ├── workload/page.tsx    # Workload management (302 lines)
│   │   ├── model/page.tsx       # Model presets (78 lines)
│   │   ├── system/page.tsx      # System/network config (474 lines)
│   │   ├── validate/page.tsx    # Pre-flight + launch (441 lines)
│   │   ├── run/[id]/page.tsx    # Live monitoring (201 lines)
│   │   └── results/[id]/page.tsx # Results analysis (425 lines)
│   ├── components/
│   │   └── topology/
│   │       └── TopologyView.tsx # SVG network visualization (305 lines)
│   ├── lib/
│   │   └── api.ts               # API client + types (345 lines)
│   ├── package.json             # pnpm 9, Next.js 14, React 18
│   └── tsconfig.json            # Strict mode
├── frameworks/                  # Git submodules
│   ├── astra-sim/               # C++ simulator
│   ├── chakra/                  # Trace format library
│   └── symbolic_tensor_graph/   # Workload generator
├── scripts/
│   ├── bootstrap.sh             # One-time setup (191 lines)
│   ├── build_backends.sh        # ASTRA-sim build (42 lines)
│   └── test/                    # Component test scripts
├── runs/                        # Per-run artifacts (gitignored)
├── CLAUDE.md                    # Developer reference
└── plan.md                      # Phase roadmap
```

---

## 2. Frontend Architecture

### 2.1 Page-to-API Mapping

Every page is a client component (`"use client"`) using React hooks for state and side effects.

| Page File | Route | API Functions Used | Purpose |
|-----------|-------|--------------------|---------|
| `app/page.tsx` | `/` | `healthCheck()`, `listRuns()` | Dashboard |
| `app/workload/page.tsx` | `/workload` | `listWorkloadLibrary()`, `listPresets()`, `generateWorkload()`, `defaultStgSpec()` | Workload management |
| `app/model/page.tsx` | `/model` | `listPresets()` | Preset viewer |
| `app/system/page.tsx` | `/system` | `listBackends()`, `validateConfigs()`, `materializeConfigs()`, `defaultSystemConfig()`, `defaultNetworkConfig()`, `defaultMemoryConfig()` | Config editor |
| `app/validate/page.tsx` | `/validate` | `listWorkloadLibrary()`, `validateRun()`, `startRun()`, `defaultMemoryConfig()`, `defaultNetworkConfig()`, `defaultSystemConfig()` | Pre-flight + launch |
| `app/run/[id]/page.tsx` | `/run/{id}` | `getRun()`, `cancelRun()`, `eventsUrl()` (SSE) | Run monitoring |
| `app/results/[id]/page.tsx` | `/results/{id}` | `getSummary()`, `getStats()`, `compareRuns()`, `timelineUrl()`, `logUrl()` | Results analysis |

### 2.2 API Client (`lib/api.ts`)

The API client is a single file (345 lines) containing:

**Base utilities:**
```typescript
const backendUrl = () => process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
function getJson<T>(path: string): Promise<T>    // GET with cache: "no-store"
function postJson<T>(path: string, body): Promise<T>  // POST with JSON content-type
```

**Type definitions**: All request/response types are co-located with their fetch functions. Key types:
- `StgSpec` — workload generation parameters (25 fields)
- `ConfigBundle` — combined system + network + memory config
- `NetworkConfig` — topology arrays (topology, npus_count, bandwidth, latency)
- `SystemConfig` — ASTRA-sim system parameters (hyphenated keys)
- `RunValidateResponse` — pre-flight check results
- `RunSummary` — aggregate simulation results
- `PerNpuRow`, `PerCollectiveRow` — tabular result data
- `CompareResult` — cross-run diff

**Default factories**: `defaultStgSpec()`, `defaultSystemConfig()`, `defaultNetworkConfig()`, `defaultMemoryConfig()` provide sensible initial values for forms.

### 2.3 State Management

No global state library. Each page manages state locally:

- **`useState`** for all mutable state (form values, API responses, loading flags, errors)
- **`useEffect`** for side effects (initial data fetch, debounced validation, SSE connections)
- **`useRef`** for DOM refs (log scroll target, EventSource connection)
- **`useMemo`** for derived values (totalNpus, prefixOptions, errorDimIdx)

**Debounced validation pattern** (used in `/system` and `/validate`):
```typescript
useEffect(() => {
  const t = setTimeout(async () => {
    const res = await validateConfigs(bundle);
    setIssues(res.issues);
  }, 200);  // 200-250ms debounce
  return () => clearTimeout(t);
}, [bundle]);
```

### 2.4 Shared Component: TopologyView

**File**: `components/topology/TopologyView.tsx` (305 lines)

Pure SVG renderer with no external dependencies. Props:
```typescript
interface Props {
  network: NetworkConfig;
  errorDimIdx?: number | null;  // highlights error dimension in red
}
```

Rendering modes:
- **0 dimensions**: empty placeholder
- **1 dimension**: `SingleDim` — circular node layout with topology-specific edges (Ring, FullyConnected, Switch hub)
- **2 dimensions**: `TwoDim` — column groups with inner topologies + dashed inter-dim links
- **3+ dimensions**: text fallback

### 2.5 Per-Page Component Breakdown

Each page defines inline sub-components. Key patterns:

| Component Pattern | Used In | Purpose |
|------------------|---------|---------|
| `FormGroup` | workload | Label + children wrapper |
| `FieldGrid` | workload, system | 2-3 column responsive grid |
| `NumField` / `NumInput` | workload, system, validate | Number input with label and constraints |
| `SelectField` | validate | Dropdown with label |
| `ErrorBox` | all pages | Red-bordered error message display |
| `SectionTitle` | system | Uppercase heading |
| `SummaryCard` / `Card` | validate, results | Title + value + unit + hint card |
| `IssueList` | system, validate | Color-coded validation issues |
| `StatusBadge` | run | Status label with color |
| `Banner` | validate | Green/amber status bar |

### 2.6 Design System

Dark-first theme using Tailwind defaults (no custom theme extensions):

| Element | Classes |
|---------|---------|
| Background | `bg-zinc-950` (page), `bg-zinc-900` (cards), `bg-zinc-900/50` (overlay) |
| Text | `text-zinc-100` (primary), `text-zinc-400` (muted), `text-zinc-500` (dim) |
| Borders | `border-zinc-800` (solid), `border-zinc-700` (dashed) |
| Success | `text-emerald-300`, `bg-emerald-950` |
| Error | `text-red-300`, `bg-red-950` |
| Warning | `text-amber-300`, `bg-amber-950` |
| Info | `text-blue-300`, `bg-blue-950` |
| Buttons | `bg-zinc-100 text-zinc-900` (primary), `border-zinc-800 text-zinc-300` (secondary) |

---

## 3. Backend Architecture

### 3.1 Module Map

```
app/
├── main.py              # FastAPI app, CORS, router mounting
├── api/                 # HTTP layer (request → response)
│   ├── workload.py      # Workload library, presets, generation
│   ├── system.py        # Config validation, materialization, backends
│   ├── runs.py          # Run validation, execution, status, SSE, cancel
│   └── results.py       # Summary, stats, timeline, logs, comparison
├── schemas/             # Pydantic models (validation + serialization)
│   ├── stg_spec.py      # StgSpec: workload generation parameters
│   ├── network_config.py # NetworkConfig: multi-dim topology
│   ├── system_config.py # SystemConfig: ASTRA-sim system params
│   └── memory_config.py # MemoryConfig: memory expansion type
├── orchestrator/        # Subprocess lifecycle management
│   ├── pipeline.py      # State machine: queued→building→running→done
│   ├── astra_runner.py  # ASTRA-sim binary: Popen + streaming + cancel
│   ├── stg_runner.py    # STG: conda subprocess for trace generation
│   └── chakra_tools.py  # Chakra: visualization wrapper
├── parsers/             # Output → structured data
│   ├── astra_logs.py    # Regex: log.log → NpuStats (wall/comm/compute)
│   └── et_traces.py     # Protobuf: .et → CollectiveOp (type/size)
├── build/               # Backend registry
│   └── backend_adapter.py # BackendAdapter dataclass + _REGISTRY dict
└── storage/             # Persistence
    ├── registry.py      # SQLModel: Run, Artifact, Preset tables
    └── fs_layout.py     # Path helpers: run_dir(), logs_dir(), etc.
```

### 3.2 Request Flow: Workload Generation

```
POST /workloads/generate  (StgSpec body)
  │
  ▼  workload.py:generate_workload()
  │   1. Create run_id via fs_layout.new_run_id()
  │   2. Create traces_dir
  │
  ▼  stg_runner.run_stg(spec, output_dir)
  │   1. Resolve STG_PYTHON (conda interpreter)
  │   2. Build CLI args from spec.to_cli_args()
  │   3. subprocess.run([python, main.py, ...], timeout=1800s)
  │   4. Glob output_dir for *.et files
  │
  ▼  workload.py (continued)
  │   1. Save spec.json to run_dir
  │   2. Insert Run + Artifact records in SQLite
  │   3. Return GenerateResponse{run_id, total_npus, trace_files, stdout_tail}
```

### 3.3 Request Flow: Simulation Run

```
POST /runs  (StartRunRequest body)
  │
  ▼  runs.py:start_run()
  │   1. Resolve workload → (prefix, et_files)
  │   2. Validate NPU count matches network config
  │   3. Create run_id, insert Run(status="queued")
  │
  ▼  pipeline.execute_pipeline_async() → background Thread
  │
  │   Step 1: Write spec.json
  │   Step 2: Get BackendAdapter from registry
  │   Step 3: _ensure_built(adapter) → subprocess build if needed
  │           status: queued → building
  │   Step 4: _materialize(bundle) → write system.json, network.yml, memory.json
  │   Step 5: astra_runner.build_invocation() → AstraInvocation
  │           status: building → running
  │   Step 6: astra_runner.stream_run(invocation)
  │           → Popen(binary, --flags...)
  │           → yield (kind, text) for each stdout line
  │           → append_event(run_id, "log", text=line)
  │   Step 7: Parse returncode
  │           returncode 0 → succeeded
  │           returncode < 0 → cancelled (signal)
  │           returncode > 0 → failed
  │   Step 8: Index CSV artifacts in DB
  │   Step 9: append_event(run_id, "done", ok=True/False)
  │
  ▼  SSE: GET /runs/{id}/events
      → Tail events.log, yield JSON lines to browser
```

### 3.4 Schema Conventions

**Pydantic v2 with aliases** for ASTRA-sim compatibility:

```python
class SystemConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scheduling_policy: Literal["LIFO", "FIFO"] = Field(
        default="LIFO", alias="scheduling-policy"
    )

    def to_json_dict(self):
        return self.model_dump(by_alias=True, exclude_none=True)
```

Python code uses `snake_case` (`scheduling_policy`). JSON output uses `hyphenated-keys` (`scheduling-policy`) matching ASTRA-sim reference configs.

**Network config** serializes to YAML via `NetworkConfig.to_yaml()` with flow-style arrays:
```yaml
topology: [ Ring ]
npus_count: [ 8 ]
bandwidth: [ 50.0 ]  # GB/s
latency: [ 500.0 ]  # ns
```

### 3.5 Storage

**SQLite** at `runs/registry.db` with three SQLModel tables:

| Table | Columns | Purpose |
|-------|---------|---------|
| `Run` | id (PK), status, created_at | Run metadata + state |
| `Artifact` | id (PK), run_id (FK), kind, path | File references per run |
| `Preset` | id (PK), kind, payload_json | Model preset cache |

**Filesystem** per run:
```
runs/<run_id>/
├── spec.json              # Full run specification (bundle + workload_prefix)
├── configs/
│   ├── system.json        # ASTRA-sim system config
│   ├── network.yml        # ASTRA-sim network config (YAML)
│   └── memory.json        # ASTRA-sim memory config
├── traces/                # .et files (if generated via STG)
├── logs/
│   ├── events.log         # JSONL event stream (SSE source)
│   ├── stdout.log         # Raw binary output
│   ├── log.log            # ASTRA-sim log
│   └── err.log            # stderr
├── previews/              # On-demand Chakra GraphML
└── stats.parquet          # Cached parsed NpuStats
```

Path helpers in `storage/fs_layout.py`:
```python
RUNS_DIR = Path(os.environ.get("SIM_RUNS_DIR", REPO_ROOT / "runs"))

def new_run_id() -> str: return uuid4().hex[:12]
def run_dir(run_id) -> Path: return RUNS_DIR / run_id
def traces_dir(run_id) -> Path: return run_dir(run_id) / "traces"
def configs_dir(run_id) -> Path: return run_dir(run_id) / "configs"
def logs_dir(run_id) -> Path: return run_dir(run_id) / "logs"
```

---

## 4. API Reference

### Health

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| GET | `/health` | `{"status": "ok"}` | Readiness probe |

### Workloads

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| GET | `/workloads/library` | — | `LibraryEntry[]` | List all .et files (examples + runs) |
| GET | `/workloads/presets` | — | `Preset[]` | List model presets from `schemas/presets/` |
| POST | `/workloads/generate` | `StgSpec` | `GenerateResponse` | Run STG to create trace files |
| GET | `/workloads/preview/{run_id}/{npu_idx}.graphml` | — | XML file | Chakra visualization (on-demand) |

**Types:**
```typescript
LibraryEntry = { source: "examples"|"run", run_id: string|null, name: string, path: string, size_bytes: number }
Preset = { id: string, label: string, model_type: string, spec: Record<string, unknown> }
GenerateResponse = { run_id: string, total_npus: number, trace_files: string[], stdout_tail: string }
```

### Configs

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| GET | `/backends` | — | `BackendInfo[]` | List available ASTRA-sim backends |
| POST | `/configs/validate` | `ConfigBundle` | `ValidateResponse` | Pre-flight validation |
| POST | `/configs/materialize` | `ConfigBundle` | `MaterializeResponse` | Write config files |
| POST | `/configs/dryrun` | raw dict | dict | Schema validation only |

**Types:**
```typescript
BackendInfo = { name: string, label: string, network_schema: string, binary_path: string, built: boolean }
ConfigBundle = { backend: string, system: SystemConfig, network: NetworkConfig, memory: MemoryConfig, expected_npus?: number|null }
ValidateResponse = { ok: boolean, issues: Issue[], total_npus: number, binary_present: boolean }
MaterializeResponse = { run_id: string, config_dir: string, files: { network: string, system: string, memory: string } }
Issue = { severity: "error"|"warning"|"info", field: string, message: string }
```

### Runs

| Method | Path | Request | Response | Description |
|--------|------|---------|----------|-------------|
| POST | `/runs/validate` | `RunValidateRequest` | `RunValidateResponse` | Full pre-flight check |
| POST | `/runs` | `StartRunRequest` | `StartRunResponse` | Start a simulation |
| GET | `/runs` | — | `RunListItem[]` | List all runs (newest first) |
| GET | `/runs/{id}` | — | `RunStatus` | Status snapshot |
| GET | `/runs/{id}/events` | — | SSE stream | Real-time event stream |
| POST | `/runs/{id}/cancel` | `{}` | `{signalled: boolean}` | SIGTERM to process |

**Types:**
```typescript
WorkloadRef = { kind: "existing"|"run", value: string, name?: string }
RunValidateRequest = { workload: WorkloadRef, bundle: ConfigBundle, smoke_run?: boolean }
RunValidateResponse = { ok: boolean, issues: Issue[], workload: WorkloadSummary|null,
                        binary_present: boolean, smoke: SmokeRunResult|null, estimated_run_seconds: number|null }
WorkloadSummary = { prefix: string, trace_count: number, total_size_bytes: number }
SmokeRunResult = { ran: boolean, returncode: number|null, stdout_tail: string,
                   stderr_tail: string, duration_sec: number|null }
StartRunRequest = { workload: WorkloadRef, bundle: ConfigBundle }
StartRunResponse = { run_id: string, status: string }
RunStatus = { run_id: string, status: string, config_dir: string|null, log_dir: string|null }
RunListItem = { run_id: string, status: string, created_at: string }
```

**SSE event format** (one JSON object per line):
```json
{"ts": "2024-01-01T00:00:00Z", "kind": "status", "status": "running"}
{"ts": "2024-01-01T00:00:01Z", "kind": "log", "text": "sys[0], Wall time: 22240"}
{"ts": "2024-01-01T00:00:02Z", "kind": "done", "ok": true, "returncode": 0}
```

### Results

| Method | Path | Query | Response | Description |
|--------|------|-------|----------|-------------|
| GET | `/results/{id}/summary` | — | `Summary` | Aggregate stats |
| GET | `/results/{id}/stats` | `view=per_npu\|per_collective\|per_collective_agg` | JSON array | Tabular data |
| GET | `/results/{id}/timeline.json` | — | Chrome Tracing JSON | For Perfetto |
| GET | `/results/{id}/spec` | — | JSON | Full run spec |
| GET | `/results/{id}/spec.yaml` | — | YAML | Spec export |
| GET | `/results/{id}/logs/{name}` | — | text file | Raw log (stdout, log, err, events) |
| GET | `/results/{id}/compare` | `with={other_id}` | `CompareResult` | Cross-run diff |

**Types:**
```typescript
Summary = { run_id: string, npu_count: number, end_to_end_cycles: number,
            slowest_npu: number|null, avg_comm_fraction: number, top_collectives: CollectiveAgg[] }
CollectiveAgg = { comm_type: string, count: number, total_bytes: number }
PerNpuRow = { npu_id: number, wall_cycles: number, comm_cycles: number,
              compute_cycles: number, exposed_comm_cycles: number, comm_fraction: number }
PerCollectiveRow = { npu_id: number, node_id: number, name: string,
                     comm_type: string, comm_size_bytes: number }
CompareResult = { a: string, b: string, summary_a: Summary, summary_b: Summary,
                  e2e_delta_cycles: number, e2e_delta_pct: number, config_diffs: FieldDiff[] }
FieldDiff = { path: string, a: unknown, b: unknown }
```

---

## 5. Custom Workload Generation

### 5.1 STG Integration

**File**: `backend/app/orchestrator/stg_runner.py`

STG runs as a subprocess using a dedicated conda environment:

```python
STG_PYTHON = os.environ.get("STG_PYTHON", "~/miniforge3/envs/stg-env/bin/python")
STG_MAIN = REPO_ROOT / "frameworks/symbolic_tensor_graph/main.py"
```

The `StgSpec.to_cli_args()` method converts Pydantic fields to CLI flags:
```python
# StgSpec(model_type="llama", dp=2, tp=4, ...) becomes:
["--model_type", "llama", "--dp", "2", "--tp", "4", ...]
```

Key parameters:
- **Timeout**: 1800 seconds (30 minutes)
- **Output**: `{output_dir}/{name}.{npu_idx}.et` files
- **NPU index extraction**: filename parsing (`workload.7.et` → NPU 7)

### 5.2 Adding Model Presets

**Directory**: `backend/app/schemas/presets/`

Create a JSON file with this format:
```json
{
  "id": "mixtral-8x7b",
  "label": "Mixtral 8x7B",
  "model_type": "moe",
  "spec": {
    "model_type": "moe",
    "dvocal": 32000,
    "dmodel": 4096,
    "dff": 14336,
    "head": 32,
    "kvhead": 8,
    "num_stacks": 32,
    "experts": 8,
    "kexperts": 2,
    "seq": 2048,
    "batch": 4,
    "dp": 1,
    "tp": 2,
    "sp": 1,
    "pp": 1,
    "ep": 4
  }
}
```

The file is automatically discovered by `GET /workloads/presets` — no code changes needed. The `spec` field is a partial `StgSpec`: any omitted fields use `defaultStgSpec()` values.

### 5.3 Chakra Tools

**File**: `backend/app/orchestrator/chakra_tools.py`

Wraps the `chakra_visualizer` CLI tool:
```python
visualize_trace(et_file, output_path, fmt="graphml", timeout_sec=120)
```

The preview endpoint (`GET /workloads/preview/{run_id}/{npu_idx}.graphml`) calls this on demand to generate GraphML files for trace inspection.

---

## 6. Custom System Configuration

### 6.1 Adding Backends

**File**: `backend/app/build/backend_adapter.py`

Add a new entry to the `_REGISTRY` dict:

```python
_REGISTRY = {
    # ... existing entries ...
    "my_backend": BackendAdapter(
        name="my_backend",
        label="My Custom Backend",
        binary_path=REPO_ROOT / "path/to/binary",
        build_cmd=["bash", "scripts/build_my_backend.sh"],
        network_schema="analytical",  # or "ns3", etc.
    ),
}
```

The `BackendAdapter` dataclass:
```python
@dataclass(frozen=True)
class BackendAdapter:
    name: str              # Unique identifier (used in ConfigBundle.backend)
    label: str             # Display name in the UI dropdown
    binary_path: Path      # Path to the compiled binary
    build_cmd: list[str]   # Command to build the binary
    network_schema: str    # Network config format type
```

After adding the entry, it automatically appears in:
- `GET /backends` response
- Frontend backend picker dropdown
- Build step during pipeline execution

### 6.2 Config Format Details

**Network (YAML)**: `NetworkConfig.to_yaml()` produces flow-style YAML:
```yaml
topology: [ Ring, FullyConnected ]
npus_count: [ 4, 4 ]
bandwidth: [ 50.0, 25.0 ]  # GB/s
latency: [ 500.0, 1000.0 ]  # ns
```

**System (JSON)**: `SystemConfig.to_json_dict()` uses hyphenated aliases and excludes None fields:
```json
{
  "scheduling-policy": "LIFO",
  "endpoint-delay": 10,
  "active-chunks-per-dimension": 1,
  "all-reduce-implementation": ["ring"],
  "local-mem-bw": 1600,
  "boost-mode": 0
}
```

**Memory (JSON)**: `MemoryConfig.to_json_dict()`:
```json
{ "memory-type": "NO_MEMORY_EXPANSION" }
```

---

## 7. Extending the System

### 7.1 New Topology Types

1. Add to `TopologyKind` literal in **backend** (`backend/app/schemas/network_config.py:18`):
   ```python
   TopologyKind = Literal["Ring", "FullyConnected", "Switch", "Mesh"]
   ```

2. Add to `TopologyKind` type in **frontend** (`frontend/lib/api.ts:99`):
   ```typescript
   export type TopologyKind = "Ring" | "FullyConnected" | "Switch" | "Mesh";
   ```

3. Update `TopologyView.tsx` — add rendering logic:
   - `nodePositions()`: define layout for new topology
   - `topologyLinks()`: define edge connections
   - Optionally add `SingleDim` variant for 1D rendering

4. Update validation in `backend/app/api/system.py` if needed (e.g., min NPU constraints).

### 7.2 New Collective Implementations

Add to `KNOWN_COLLECTIVES` set in `backend/app/api/runs.py` (around line 55):
```python
KNOWN_COLLECTIVES = {
    "ring", "direct", "halvingDoubling", "doubleBinaryTree",
    "oneRing", "oneDirect",
    "myNewAlgorithm",  # ← add here
}
```

Custom collectives prefixed with `custom-` are already passed through without warnings.

### 7.3 New Result Views

1. Add to `view` query parameter options in `backend/app/api/results.py:159`:
   ```python
   view: Literal["per_npu", "per_collective", "per_collective_agg", "my_view"]
   ```

2. Implement the query logic in `get_stats()` function.

3. Add a new tab in `frontend/app/results/[id]/page.tsx`:
   - Add tab button to the tab bar
   - Create a `MyViewTab` component
   - Fetch data via `getStats(runId, "my_view")`

### 7.4 New Parsers

Follow the existing pattern:

**For log-based parsing** (like `astra_logs.py`):
```python
@dataclass(frozen=True)
class MyStats:
    field1: int
    field2: float

def parse_my_log(log_path: Path) -> list[MyStats]:
    # Regex extraction from log lines
    ...

def to_dataframe(stats: list[MyStats]) -> pd.DataFrame:
    return pd.DataFrame([asdict(s) for s in stats])
```

**For protobuf-based parsing** (like `et_traces.py`):
```python
def parse_et_custom(et_path: Path, npu_id: int) -> list[MyOp]:
    with open(et_path, "rb") as f:
        # Read protobuf messages, filter/transform
        ...
```

---

## 8. Testing Guide

### 8.1 Running Tests

```bash
# Activate the backend venv
source .venv-backend/bin/activate

# All unit + integration tests (no binary needed)
cd backend && pytest tests/unit tests/integration -q

# With coverage report
cd backend && pytest --cov=app --cov-report=term-missing

# Coverage with threshold
cd backend && pytest --cov=app --cov-fail-under=80

# Smoke tests only (requires ASTRA-sim binary)
cd backend && pytest tests/smoke -q

# All tests
cd backend && pytest -q

# Lint
cd backend && ruff check .

# Frontend type-check + build
cd frontend && pnpm build

# Frontend lint
cd frontend && pnpm lint
```

### 8.2 Test Organization

```
tests/
├── conftest.py              # Fixtures: app (FastAPI), client (httpx AsyncClient)
├── unit/
│   ├── test_schemas.py      # StgSpec, NetworkConfig, SystemConfig, MemoryConfig validation
│   ├── test_backend_adapter.py  # Backend registry lookup, is_built check
│   ├── test_parsers.py      # NpuStats parsing, CollectiveOp extraction
│   └── test_health.py       # GET /health
├── integration/
│   ├── test_api_health.py   # /health, /backends, /workloads/*, /configs/*, /runs/validate
│   └── test_api_results.py  # /results/{id}/* (summary, stats, timeline, spec, logs, compare)
└── smoke/
    └── test_reference_runs.py  # End-to-end runs, cycle count verification
```

**Unit tests** — pure functions, no I/O:
- Import directly from `app.schemas.*` or `app.parsers.*`
- Test validation rules, serialization, CLI arg generation
- Fast (~1s total)

**Integration tests** — API via httpx ASGI transport:
- Use `client` fixture (async httpx client bound to the FastAPI app)
- Test endpoints with real request/response cycles
- Isolated via `SIM_RUNS_DIR` tmpdir
- Medium speed (~3s total)

**Smoke tests** — require ASTRA-sim binary:
- Gated with `@pytest.mark.skipif(not is_built(get_backend("analytical_cu"))))`
- Start real simulations, poll for completion, verify exact cycle counts
- Reference values: `reduce_scatter 4NPU → 22240 cycles`, `all_reduce 4NPU → 43000 cycles`
- Slow (~5s per test)

### 8.3 Test Infrastructure

**Root `conftest.py`** (`backend/conftest.py`):
```python
# Runs BEFORE any module import
# Isolates tests from real runs/ directory
import tempfile, os
tmp = tempfile.mkdtemp(prefix="sim-test-")
os.environ["SIM_RUNS_DIR"] = tmp
```

This is critical because `app/storage/registry.py` reads `SIM_RUNS_DIR` at import time.

**Test `conftest.py`** (`backend/tests/conftest.py`):
```python
@pytest.fixture
def app():
    from app.main import app
    init_db()
    yield app

@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

### 8.4 Writing New Tests

**Unit test pattern:**
```python
def test_my_schema_validation():
    # Arrange
    spec = StgSpec(dmodel=4096, head=32, kvhead=8)

    # Act
    result = spec.to_cli_args()

    # Assert
    assert "--dmodel" in result
    assert result[result.index("--dmodel") + 1] == "4096"
```

**Integration test pattern:**
```python
@pytest.mark.asyncio
async def test_my_endpoint(client):
    # Arrange
    payload = {"backend": "analytical_cu", ...}

    # Act
    resp = await client.post("/configs/validate", json=payload)

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
```

**Smoke test pattern:**
```python
BINARY = get_backend("analytical_cu").binary_path

@pytest.mark.skipif(not BINARY.exists(), reason="binary not built")
@pytest.mark.asyncio
async def test_reference_run(client):
    # Start run
    resp = await client.post("/runs", json={...})
    run_id = resp.json()["run_id"]

    # Poll until done
    for _ in range(30):
        status = (await client.get(f"/runs/{run_id}")).json()["status"]
        if status in ("succeeded", "failed"):
            break
        await asyncio.sleep(1)

    # Verify
    summary = (await client.get(f"/results/{run_id}/summary")).json()
    assert summary["end_to_end_cycles"] == 22240
```

### 8.5 Coverage

Target: **80%+** (current: 81%)

```bash
# View uncovered lines
pytest --cov=app --cov-report=term-missing

# HTML report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

Configured in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### 8.6 Component Test Scripts

Shell-based test scripts in `scripts/test/` provide curl-level API testing:

| Script | What it tests | Binary needed? |
|--------|--------------|----------------|
| `test_backend_health.sh` | Backend startup + health check | No |
| `test_workload_api.sh` | Library, presets, generation | No (debug model) |
| `test_config_api.sh` | Validate, materialize, error cases | No |
| `test_run_lifecycle.sh` | Start → poll → results | Yes |
| `test_frontend_build.sh` | TypeScript + ESLint | No |
| `test_full_pipeline.sh` | End-to-end pipeline | Yes |

Run all:
```bash
# Backend must be running for API tests
for f in scripts/test/test_*.sh; do bash "$f"; done
```

---

## 9. Debugging Guide

### 9.1 Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `FileNotFoundError: stg-env/bin/python` | STG conda env not created | Re-run `bootstrap.sh` or set `STG_PYTHON` env var |
| `Binary not found` on run start | ASTRA-sim not built | `FORCE=1 bash scripts/build_backends.sh` |
| Build fails with `cstdint` error | GCC 13+ missing include | Bootstrap patches this automatically; re-run bootstrap |
| `pip install -e chakra` fails | PEP 660 incompatibility | Bootstrap strips setup.cfg/setup.py; re-run bootstrap |
| NPU count mismatch error | Traces ≠ prod(npus_count) | Ensure workload NPU count matches network dimensions |
| 422 Unprocessable Entity | Pydantic validation failure | Check request body against schema; use `/configs/dryrun` for details |
| Frontend `fetch` error | Backend not running or wrong URL | Start backend; check `NEXT_PUBLIC_BACKEND_URL` |
| SSE not connecting | Wrong events URL | Check browser console; ensure run_id exists |

### 9.2 Log Locations

**Per-run logs** (`runs/<run_id>/logs/`):

| File | Format | Content |
|------|--------|---------|
| `events.log` | JSONL | All events: status changes, log lines, done sentinel |
| `stdout.log` | Plain text | Raw ASTRA-sim stdout/stderr (parsed for stats) |
| `log.log` | Plain text | ASTRA-sim's own log (contains `sys[N], Wall time:` lines) |
| `err.log` | Plain text | stderr only |

**SQLite database** (`runs/registry.db`):
```bash
# Quick inspection
sqlite3 runs/registry.db "SELECT id, status, created_at FROM run ORDER BY created_at DESC LIMIT 10;"
```

**Backend server logs**: stdout of `uvicorn app.main:app --reload`

### 9.3 SSE Debugging

The SSE endpoint (`GET /runs/{id}/events`) works by tailing `events.log`:

- **Poll interval**: 250ms (0.25 seconds)
- **Idle timeout**: 5 minutes (300 seconds) — stream closes if no new events
- **Reconnection**: browser's EventSource auto-reconnects; stream replays from file start
- **Multiple tabs**: safe — all tabs read the same file independently

**Debug SSE from terminal:**
```bash
curl -N http://localhost:8000/runs/<run_id>/events
```

**Check events.log directly:**
```bash
cat runs/<run_id>/logs/events.log | python -m json.tool --no-ensure-ascii
```

### 9.4 Pipeline State Machine

```
queued ──▶ building ──▶ running ──▶ succeeded (returncode 0)
                                ├──▶ failed    (returncode > 0)
                                └──▶ cancelled (returncode < 0, signal)
```

Each state transition:
1. Updates `Run.status` in SQLite
2. Appends a `{"kind": "status", "status": "..."}` event to events.log
3. The SSE endpoint picks up the event and streams it to the browser

**Negative returncodes** mean the process was killed by a signal:
- `-15` = SIGTERM (user cancellation via Cancel button)
- `-9` = SIGKILL (timeout or external kill)

**To manually inspect a stuck run:**
```bash
# Check status in DB
sqlite3 runs/registry.db "SELECT status FROM run WHERE id = '<run_id>';"

# Check events log
tail runs/<run_id>/logs/events.log

# Check if process is still running
ps aux | grep AstraSim
```

### 9.5 Backend CORS

The backend allows CORS from `http://localhost:3000` (configured in `app/main.py`). If running the frontend on a different port or host, update the CORS middleware:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://myhost:3000"],
    ...
)
```

### 9.6 Database Reset

To reset all run data:
```bash
rm -rf runs/
# Restart the backend — init_db() recreates the schema
```

To reset only the database (keep files):
```bash
rm runs/registry.db
# Restart the backend
```
