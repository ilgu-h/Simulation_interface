# Simulation Interface — User Manual

> Dashboard that orchestrates **STG → Chakra → ASTRA-sim** to simulate LLM training on configurable distributed hardware.

---

## Table of Contents

1. [Installation & Setup](#1-installation--setup)
2. [Quick Start — First Simulation in 5 Minutes](#2-quick-start--first-simulation-in-5-minutes)
3. [Web Interface Guide](#3-web-interface-guide)
4. [Workload Management](#4-workload-management)
5. [System Configuration](#5-system-configuration)
6. [Running Simulations](#6-running-simulations)
7. [Interpreting Results](#7-interpreting-results)
8. [Glossary](#8-glossary)

---

## 1. Installation & Setup

### 1.1 System Prerequisites

Install the following on a Debian/Ubuntu system:

```bash
sudo apt update && sudo apt install -y \
  git cmake protobuf-compiler build-essential \
  curl wget python3 python3-venv python3-pip
```

You also need **Node.js 20+** with corepack:

```bash
# If not already installed
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### 1.2 Running bootstrap.sh

The bootstrap script is **idempotent** — safe to re-run at any time. It performs 8 steps:

```bash
cd /path/to/Simulation_interface
bash scripts/bootstrap.sh
```

| Step | What it does |
|------|-------------|
| 1 | Verify prerequisites (git, cmake, protoc, node, curl) |
| 2 | Initialize git submodules (astra-sim analytical sub-submodules) |
| 3 | Apply vendored patches (cxxopts.hpp for GCC 13+, Chakra PEP 660 fix, protobuf stubs) |
| 4 | Install Miniforge to `~/miniforge3` (conda-forge Python) |
| 5 | Create `stg-env` conda environment for STG trace generation |
| 6 | Enable pnpm via corepack |
| 7 | Create `.venv-backend` Python venv, install Chakra (editable) and backend |
| 8 | Build ASTRA-sim analytical backend binaries |

The entire process takes 10–20 minutes depending on your system.

### 1.3 Verifying the Build

After bootstrap completes, verify each component:

```bash
# 1. Backend health check
source .venv-backend/bin/activate
cd backend && uvicorn app.main:app --port 8000 &
curl -sf http://localhost:8000/health
# Expected: {"status":"ok"}

# 2. ASTRA-sim binary
./frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware --help

# 3. Frontend build
cd frontend && pnpm install && pnpm build
```

### 1.4 Starting the Dev Stack

Open **two terminals**:

**Terminal 1 — Backend (FastAPI):**
```bash
source .venv-backend/bin/activate
cd backend
uvicorn app.main:app --reload
# Runs at http://localhost:8000
```

**Terminal 2 — Frontend (Next.js):**
```bash
cd frontend
pnpm dev
# Runs at http://localhost:3000
```

Open your browser to **http://localhost:3000**.

### 1.5 Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` | Frontend → backend connection |
| `SIM_RUNS_DIR` | `<repo>/runs` | Where per-run artifacts are stored |
| `STG_PYTHON` | `~/miniforge3/envs/stg-env/bin/python` | Python interpreter for STG |

### 1.6 Docker

Run the entire stack in containers with a single command:

```bash
docker compose up --build
# backend → http://localhost:8000
# frontend → http://localhost:3000
```

To run in the background:

```bash
docker compose up --build -d
docker compose logs -f          # tail logs
docker compose down             # stop all services
```

> **Note:** The Docker install should use the official apt repository (not snap) for full systemd integration. The `.dockerignore` file ensures host virtualenvs and `node_modules` do not interfere with the container build.

---

## 2. Quick Start — First Simulation in 5 Minutes

Follow these steps for your first end-to-end simulation run:

### Step 1: Start the stack
Start the backend and frontend as described in [Section 1.4](#14-starting-the-dev-stack).

### Step 2: Generate a workload
1. Navigate to **http://localhost:3000/workload**
2. Click the **"Generate new"** tab
3. Select the **LLaMA-7B** preset from the dropdown — this fills in model parameters automatically
4. Set parallelism: **DP=2, TP=2** (other defaults are fine)
5. Notice the **Total NPUs: 4** indicator updates
6. Click **"Generate 4 traces"**
7. Wait for the green success panel showing run_id and trace file paths

### Step 3: Configure the system
1. Navigate to **http://localhost:3000/system**
2. Keep the defaults: **Ring** topology, **4 NPUs**, **50 GB/s** bandwidth, **500 ns** latency
3. Verify the topology SVG preview shows 4 nodes in a ring
4. Click **"Materialize"** to write the config files

### Step 4: Validate and run
1. Navigate to **http://localhost:3000/validate**
2. Select your generated workload prefix from the quick-pick buttons
3. Check the summary cards: Traces (4), NPUs (4, green match), Binary (ready)
4. Verify the green **"Pre-flight OK"** banner appears
5. Click **"Start run →"**

### Step 5: Monitor
You're redirected to the **Run Monitor** page (`/run/[id]`).
- Watch the live log stream as the simulation executes
- Status progresses: queued → building → running → succeeded
- Typical runtime: 1–5 seconds for small workloads

### Step 6: View results
Once status shows **succeeded**, click **"Results →"**:
- **Summary tab**: end-to-end cycles, NPU count, communication fraction
- **Per-NPU tab**: per-NPU wall time with stacked bar chart
- **Timeline tab**: download the Chrome Tracing JSON, open in [ui.perfetto.dev](https://ui.perfetto.dev)

---

## 3. Web Interface Guide

### 3.1 Dashboard (`/`)

The home page provides:

- **Backend status indicator**: green "Backend is reachable" or red error message
- **4 navigation cards**: quick links to Workload, Model Presets, System/Network, and Validate & Run pages
- **Recent runs table**: last 10 simulation runs with:

| Column | Description |
|--------|-------------|
| Run ID | 12-character hex identifier (clickable) |
| Status | Color-coded: queued (gray), building (amber), running (blue), succeeded (green), failed (red), cancelled (gray) |
| Time | When the run was created |

Clicking a **succeeded** run goes to Results; other statuses go to the Run Monitor.

### 3.2 Workload Page (`/workload`)

Two tabs for managing workload traces:

#### "Select existing" tab
A table of all available `.et` trace files from two sources:
- **examples**: bundled microbenchmarks in `frameworks/astra-sim/examples/workload/`
- **run**: traces from previous workload generation runs

| Column | Description |
|--------|-------------|
| Source | `examples` or `run` |
| Name | Trace file name (e.g., `all_reduce.0.et`) |
| Run ID | Associated run ID (null for examples) |
| Size | File size in bytes/KB/MB |

#### "Generate new" tab
Create new workload traces using STG (Symbolic Tensor Graph):

1. **Preset picker**: dropdown to load a model preset (LLaMA-7B, LLaMA-70B, GPT3-175B)
2. **Model type**: dense, llama, gpt, moe, or debug
3. **Parallelism grid**: DP, TP, SP, PP, EP (EP only active for MoE models)
4. **Model shape**: dmodel, dff, head, kvhead, num_stacks, dvocal
5. **Training shape**: batch, seq, micro_batch
6. **Total NPUs indicator**: computed as `DP × TP × SP × PP × EP`
7. **Toggle flags**: weight_sharded, activation_recompute, tpsp, mixed_precision
8. **Generate button**: starts trace generation (takes 10–60 seconds)
9. **Result panel**: shows run_id, list of generated trace files, stdout output

### 3.3 Model Presets (`/model`)

Displays the 3 built-in model presets as cards:

| Preset | Parameters | Total NPUs |
|--------|-----------|------------|
| **LLaMA-7B** | dmodel=4096, dff=11008, head=32, kvhead=32, 32 layers | 1 (TP=1, PP=1) |
| **LLaMA-70B** | dmodel=8192, dff=28672, head=64, kvhead=8, 80 layers | 8 (TP=8) |
| **GPT3-175B** | dmodel=12288, dff=49152, head=96, kvhead=96, 96 layers | 64 (TP=8, PP=8) |

Each card has a **"Use in workload →"** button linking to the Workload page.

**Adding new presets**: Drop a JSON file into `backend/app/schemas/presets/` — it appears automatically in the UI. See [Section 4.3](#43-adding-model-presets) for the format.

### 3.4 System/Network Config (`/system`)

A two-column layout for configuring the simulation environment:

#### Left column — Configuration
- **Backend picker**: dropdown selecting the simulation backend (Analytical Congestion Unaware, Analytical Congestion Aware, or NS-3 stub). Shows "built" or "needs build" status.
- **Network section**: multi-dimensional topology editor
  - Each dimension row has: topology type (Ring/FullyConnected/Switch), NPU count, bandwidth (GB/s), latency (ns), delete button
  - **"+ add dim"** button adds a new dimension with defaults (Ring, 2 NPUs, 50 GB/s, 500 ns)
  - Total NPUs = product of all dimension NPU counts
- **System section**: scheduling policy (LIFO/FIFO), endpoint-delay, active-chunks-per-dimension, preferred-dataset-splits, local-mem-bw, boost-mode, four collective implementation fields, collective-optimization
- **Memory note**: currently fixed to NO_MEMORY_EXPANSION
- **Materialize button**: writes config files to disk (creates a run directory)

#### Right column — Preview & validation
- **Topology SVG**: live visualization of the network topology (Ring, FullyConnected, or Switch)
- **Issue list**: validation errors (red), warnings (amber), and info (gray) from real-time validation
- **Materialized output**: green success box with run_id and file paths after materialization

### 3.5 Validate & Run (`/validate`)

Pre-flight checks and simulation launch:

#### Left column
- **Workload prefix input**: text input with quick-select buttons for available trace prefixes
- **Network override fields**: inline dimension-0 settings (NPUs, bandwidth, latency, all-reduce implementation)
- **Topology preview**: SVG of the configured topology
- **Summary cards** (4 cards):
  - **Traces**: count + size hint
  - **NPUs**: product of npus_count with match/mismatch indicator
  - **Binary**: ready or missing (shows backend name)
  - **Est. wall**: rough estimate in milliseconds
- **Smoke button**: runs a quick 4-NPU test against bundled microbenchmarks
- **Start run button**: launches the full simulation

#### Right column
- **Status banner**: green "Pre-flight OK" or amber "Pre-flight blocked"
- **Error list**: red severity issues that block the run
- **Warning list**: amber warnings (non-blocking)

### 3.6 Run Monitor (`/run/[id]`)

Live simulation monitoring via Server-Sent Events (SSE):

- **Header**: run ID, log directory path, color-coded status badge
- **Action bar**:
  - Cancel button (active during queued/building/running)
  - Results link (active only when succeeded)
  - Line counter and "live" / "done at" indicator
- **Log pane**: scrolling terminal-style view with color-coded lines:
  - Red: errors (`[error]`, `[build:err]`)
  - Amber: build progress (`[build]`)
  - Blue: simulation progress (`[run]`)
  - Gray: cancellation messages

### 3.7 Results (`/results/[id]`)

Six tabs for analyzing simulation output:

#### Summary tab
Four metric cards:
- **End-to-end**: total simulation cycles (max wall across all NPUs)
- **NPUs**: number of processing units simulated
- **Slowest NPU**: which NPU had the highest wall time
- **Comm fraction**: average communication fraction across all NPUs (percentage)

Plus a **Top Collectives** table showing the most frequent collective operations.

#### Per-NPU tab
Table with per-NPU breakdown and inline stacked bar chart:

| Column | Description |
|--------|-------------|
| NPU | NPU identifier (0-indexed) |
| Wall (cycles) | Total execution time for this NPU |
| Comm (cycles) | Time spent in communication |
| Compute (cycles) | Time spent in computation (wall − comm) |
| Comm % | Communication fraction (comm / wall) |
| Bar | Stacked bar: blue = comm, green = compute |

#### Per-Collective tab
Table of every collective operation extracted from `.et` traces:

| Column | Description |
|--------|-------------|
| NPU | Which NPU this collective belongs to |
| Type | ALL_REDUCE, ALL_GATHER, REDUCE_SCATTER, ALL_TO_ALL, etc. |
| Name | Operation name from the trace |
| Bytes | Data size of the collective |

#### Timeline tab
- Download link for **Chrome Tracing JSON**
- Open the downloaded file at [ui.perfetto.dev](https://ui.perfetto.dev) or `chrome://tracing`
- Shows compute and communication bands per NPU, plus collective instant markers
- Note: timestamps are approximate (analytical backend doesn't emit per-collective timing)

#### Logs tab
Direct links to raw log files:
- `log.log` — ASTRA-sim's own output
- `stdout.log` — merged stdout/stderr from the simulation process
- `err.log` — stderr only
- `events.log` — JSONL event stream (status changes, log lines, done sentinel)

#### Compare tab
Side-by-side comparison of two runs:
1. Enter another run's ID in the text field (or use `?compare=<id>` URL parameter)
2. Click **Compare**
3. View:
   - **A wall** and **B wall**: end-to-end cycles for each run
   - **Delta B − A**: cycle difference and percentage (green if faster, amber if slower)
   - **Config diffs table**: every config parameter that differs between the two runs

---

## 4. Workload Management

### 4.1 Existing Traces

The workload library scans two locations:
1. **Bundled examples**: `frameworks/astra-sim/examples/workload/` — microbenchmarks for all_reduce, reduce_scatter, all_gather, all_to_all (various NPU counts and message sizes)
2. **Generated traces**: `runs/<run_id>/traces/` — output from previous STG workload generation

Each `.et` file is a **Chakra Execution Trace** (protobuf format) representing one NPU's computation and communication graph.

### 4.2 Generating Traces with STG

The Symbolic Tensor Graph (STG) generates traces modeling an LLM training iteration. Here are all configurable parameters:

#### Parallelism dimensions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dp` | 1 | Data Parallel degree — splits the global batch |
| `tp` | 1 | Tensor Parallel degree — splits model layers (columns/rows) |
| `sp` | 1 | Sequence Parallel degree — splits the sequence dimension |
| `pp` | 1 | Pipeline Parallel degree — splits model stages |
| `ep` | 1 | Expert Parallel degree — splits MoE experts (only for model_type=moe) |

**Total NPUs** = `dp × tp × sp × pp` (× `ep` if model_type is moe)

#### Model shape

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dmodel` | 8192 | Hidden dimension (must be divisible by `head`) |
| `dff` | 28672 | Feed-forward dimension |
| `head` | 64 | Number of attention heads (must be divisible by `kvhead`) |
| `kvhead` | 8 | Number of KV heads (for Grouped Query Attention) |
| `num_stacks` | 80 | Number of transformer blocks |
| `dvocal` | 32000 | Vocabulary size |

#### Training shape

| Parameter | Default | Description |
|-----------|---------|-------------|
| `batch` | 64 | Global batch size |
| `micro_batch` | -1 | Micro-batch size (-1 = auto) |
| `seq` | 1024 | Sequence length |

#### Flags

| Parameter | Default | Description |
|-----------|---------|-------------|
| `model_type` | dense | Model architecture: dense, llama, gpt, moe, debug |
| `weight_sharded` | false | Whether weights are sharded across TP ranks |
| `activation_recompute` | false | Enable activation checkpointing |
| `tpsp` | true | Enable TP-SP overlap |
| `mixed_precision` | false | Enable mixed precision (FP16/BF16) |

#### Validation rules
- `dmodel` must be divisible by `head`
- `head` must be divisible by `kvhead`
- `kexperts` must be ≤ `experts`

### 4.3 Adding Model Presets

Drop a JSON file into `backend/app/schemas/presets/`. Format:

```json
{
  "id": "my-model",
  "label": "My Custom Model",
  "model_type": "llama",
  "spec": {
    "model_type": "llama",
    "dvocal": 32000,
    "dmodel": 4096,
    "dff": 11008,
    "head": 32,
    "kvhead": 32,
    "num_stacks": 32,
    "seq": 2048,
    "batch": 4,
    "dp": 1,
    "tp": 1,
    "sp": 1,
    "pp": 1,
    "ep": 1
  }
}
```

The preset appears automatically in the UI — no code changes needed.

### 4.4 Trace Output Format

STG generates one `.et` file per NPU:
```
workload.0.et    # NPU 0's execution trace
workload.1.et    # NPU 1's execution trace
...
workload.N.et    # NPU N's execution trace
```

Each file is a protobuf-encoded **Chakra Execution Trace** containing:
- **COMP_NODE**: computation operations (matmul, layernorm, etc.)
- **COMM_COLL_NODE**: collective communication operations (all_reduce, all_gather, etc.)
- **COMM_SEND_NODE / COMM_RECV_NODE**: point-to-point communication
- **Dependencies**: edges between nodes defining execution order

---

## 5. System Configuration

### 5.1 Network Configuration

The network config defines the multi-dimensional interconnect topology.

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `topology` | list of strings | Topology type per dimension: `Ring`, `FullyConnected`, or `Switch` |
| `npus_count` | list of ints | NPU count per dimension (total = product of all) |
| `bandwidth` | list of floats | Link bandwidth in **GB/s** per dimension |
| `latency` | list of floats | Link latency in **nanoseconds** per dimension |

All lists must have the same length (one entry per dimension).

#### Topology types

| Topology | Description | Min NPUs |
|----------|-------------|----------|
| **Ring** | Bidirectional ring — each NPU connects to 2 neighbors | 2 |
| **FullyConnected** | All-to-all — every NPU connects to every other | 2 |
| **Switch** | Star — all NPUs connect through a central switch | 2 |

#### Multi-dimensional example

A 2D topology with 4 nodes per inner ring and 4 rings:
```yaml
topology: [ Ring, Ring ]
npus_count: [ 4, 4 ]      # Total: 4 × 4 = 16 NPUs
bandwidth: [ 50.0, 25.0 ]  # 50 GB/s intra-ring, 25 GB/s inter-ring
latency: [ 500.0, 1000.0 ] # 500 ns intra, 1000 ns inter
```

### 5.2 System Configuration

| Field | Default | Description |
|-------|---------|-------------|
| `scheduling-policy` | LIFO | Order for processing collective chunks: LIFO (last-in-first-out) or FIFO |
| `endpoint-delay` | 10 | Fixed delay in nanoseconds at each endpoint |
| `active-chunks-per-dimension` | 1 | Number of active chunks per dimension for chunked collectives |
| `preferred-dataset-splits` | 4 | Number of splits for data-parallel gradient reduction |
| `local-mem-bw` | 1600 | Local memory bandwidth in GB/s |
| `boost-mode` | 0 | Enable (1) or disable (0) performance boost mode |
| `collective-optimization` | localBWAware | Optimization strategy: `localBWAware` or empty string |

#### Collective implementations

Each collective operation type can use a different algorithm:

| Field | Default | Description |
|-------|---------|-------------|
| `all-reduce-implementation` | `["ring"]` | Algorithm for all-reduce operations |
| `all-gather-implementation` | `["ring"]` | Algorithm for all-gather operations |
| `reduce-scatter-implementation` | `["ring"]` | Algorithm for reduce-scatter operations |
| `all-to-all-implementation` | `["ring"]` | Algorithm for all-to-all operations |

Available algorithms:
- `ring` — Ring-based collective (default, good general-purpose)
- `direct` — Direct send/receive
- `halvingDoubling` — Halving-doubling algorithm
- `doubleBinaryTree` — Double binary tree algorithm
- `oneRing` — Single-ring variant
- `oneDirect` — Single-direct variant

The list supports one entry per network dimension. For multi-dimensional networks, specify one implementation per dimension: `["ring", "direct"]`.

### 5.3 Memory Configuration

Currently only one option:
```json
{ "memory-type": "NO_MEMORY_EXPANSION" }
```

Remote memory expansion types may be added in future phases.

### 5.4 Backend Selection

| Backend | Description |
|---------|-------------|
| **Analytical Congestion Unaware** (`analytical_cu`) | Fast analytical model — no congestion modeling. Best for quick iteration. |
| **Analytical Congestion Aware** (`analytical_ca`) | Analytical model with congestion — more accurate but slower. |
| **NS-3** (`ns3`) | Packet-level network simulation (stub — not yet built). |

---

## 6. Running Simulations

### 6.1 Pre-flight Validation

The **Validate & Run** page (`/validate`) performs these checks before allowing a run:

| Check | Severity | Description |
|-------|----------|-------------|
| Workload exists | error | Trace files must be found on disk |
| NPU count match | error | Number of trace files must equal product of `npus_count` |
| Binary present | error | Selected backend binary must be built |
| Collective known | warning | Unknown collective implementations trigger a warning |
| Switch min NPUs | error | Switch topology requires ≥ 2 NPUs |

A run **cannot start** if any error-severity issue exists. Warnings are informational.

### 6.2 Smoke Testing

The smoke test runs a quick 4-NPU simulation using bundled microbenchmarks:

- Workload: `reduce_scatter/4npus_1MB`
- Network: Ring, 4 NPUs
- Expected result: ~22,240 cycles, completes in < 2 seconds

Use the **"Smoke (4-NPU bundled)"** button on the Validate page. Results show:
- Return code (0 = success)
- Duration in seconds
- Expandable stdout/stderr output

### 6.3 Pipeline State Machine

```
queued → building → running → succeeded
                           ↘ failed
                           ↘ cancelled
```

| State | What's happening |
|-------|-----------------|
| **queued** | Run created, waiting to start |
| **building** | Building ASTRA-sim binary (if not already built) |
| **running** | ASTRA-sim simulation in progress |
| **succeeded** | Simulation completed successfully (returncode 0) |
| **failed** | Simulation error (non-zero returncode) |
| **cancelled** | User cancelled via the Cancel button |

### 6.4 Live Monitoring

The Run Monitor page uses **Server-Sent Events (SSE)** to stream log lines in real time:
- Lines are color-coded by type (errors in red, build progress in amber, simulation in blue)
- The log pane auto-scrolls to the bottom as new lines arrive
- If you navigate away and return, the SSE stream replays from the beginning of the events log

### 6.5 Cancellation

Click the **Cancel** button on the Run Monitor page to stop a running simulation:
- Sends SIGTERM to the ASTRA-sim process
- Status changes to `cancelled`
- Partial results may be available in the logs

---

## 7. Interpreting Results

### 7.1 Summary Metrics

| Metric | Description |
|--------|-------------|
| **End-to-end cycles** | Maximum wall time across all NPUs (the slowest NPU determines total time) |
| **NPU count** | Number of NPUs in the simulation |
| **Slowest NPU** | The NPU with the highest wall_cycles (the bottleneck) |
| **Avg comm fraction** | Average ratio of communication time to total time across all NPUs (0.0 = pure compute, 1.0 = pure communication) |
| **Top collectives** | Most frequent collective operations by count and total data volume |

**What to look for:**
- High comm fraction (> 50%) suggests the workload is communication-bound — consider increasing bandwidth or reducing parallelism dimensions
- If slowest NPU is consistently the same one, check for load imbalance in the workload

### 7.2 Per-NPU Stats

| Field | Description | How to interpret |
|-------|-------------|-----------------|
| `wall_cycles` | Total time from start to finish for this NPU | Lower is better; ideally uniform across NPUs |
| `comm_cycles` | Time spent waiting for or executing communication | Includes all collective operations |
| `compute_cycles` | Time spent on computation (`wall - comm`) | Pure math/memory operations |
| `exposed_comm_cycles` | Communication time not overlapped with compute | The "wasted" communication time |
| `comm_fraction` | Ratio: `comm / wall` | 0% = pure compute, 100% = pure communication |

**The stacked bar chart** shows each NPU's time split between communication (blue) and compute (green). Ideally, all bars should be similar height (balanced load).

**Common patterns:**
- **Uniform bars, low comm**: well-balanced, compute-bound workload
- **Uniform bars, high comm**: communication-bound — try reducing inter-node traffic (lower TP, increase DP)
- **Uneven bars**: load imbalance — check pipeline parallelism staging or MoE expert distribution

### 7.3 Per-Collective Stats

Each row represents a single collective operation from the trace:

| Field | Description |
|-------|-------------|
| `npu_id` | Which NPU this operation belongs to |
| `node_id` | Unique node identifier in the execution graph |
| `name` | Human-readable operation name from STG |
| `comm_type` | Collective type: ALL_REDUCE, ALL_GATHER, REDUCE_SCATTER, ALL_TO_ALL, BROADCAST, BARRIER |
| `comm_size_bytes` | Data volume of this collective in bytes |

**What to look for:**
- Large ALL_REDUCE operations often dominate training communication (gradient synchronization)
- ALL_GATHER and REDUCE_SCATTER pairs indicate tensor parallelism overhead
- Very small collectives with high frequency may indicate unnecessary synchronization

### 7.4 Timeline

The timeline tab provides a **Chrome Tracing JSON** file compatible with:
- [Perfetto UI](https://ui.perfetto.dev) (recommended)
- Chrome DevTools (`chrome://tracing`)

The timeline shows:
- **Per-NPU compute band**: one horizontal bar per NPU showing compute duration
- **Per-NPU comm band**: communication duration overlaid
- **Collective markers**: instant events at NPU 0 for each collective operation

> **Note**: The analytical backend does not emit per-collective timestamps. The timeline uses approximate placement assuming a 1 GHz clock (1 cycle = 1 microsecond).

### 7.5 Comparing Runs

Use the Compare tab to analyze differences between two simulation runs:

1. Enter the other run's ID and click Compare (or use the URL: `/results/<id>?compare=<other_id>`)
2. The comparison shows:
   - **A wall** and **B wall**: end-to-end cycles for each run
   - **Delta B − A**: the difference in cycles and percentage
     - Green: run B is faster than A
     - Amber: run B is slower than A
   - **Config diffs**: a table showing every parameter that differs between the two runs' configurations

**Typical comparison scenarios:**
- Different bandwidths (e.g., 50 GB/s vs 100 GB/s) — see how interconnect speed affects total time
- Different topologies (Ring vs FullyConnected) — compare routing efficiency
- Different collective algorithms (ring vs halvingDoubling) — benchmark algorithm performance
- Different parallelism strategies (TP=8 vs TP=4,PP=2) — find optimal decomposition

---

## 8. Glossary

| Term | Definition |
|------|-----------|
| **NPU** | Neural Processing Unit — a single accelerator (GPU, TPU, or abstract processing element) in the simulation |
| **DP (Data Parallel)** | Parallelism strategy that splits the training batch across NPUs; each NPU has a full model copy |
| **TP (Tensor Parallel)** | Parallelism strategy that splits individual tensor operations (matmul columns/rows) across NPUs |
| **SP (Sequence Parallel)** | Parallelism strategy that splits the sequence dimension across NPUs |
| **PP (Pipeline Parallel)** | Parallelism strategy that splits model layers into stages, each stage on different NPU(s) |
| **EP (Expert Parallel)** | Parallelism strategy for MoE models that distributes experts across NPUs |
| **MoE (Mixture of Experts)** | Model architecture where each token is routed to a subset of "expert" sub-networks |
| **wall_cycles** | Total execution time for one NPU from start to finish, measured in clock cycles |
| **comm_cycles** | Time spent by one NPU on communication (collective operations) |
| **compute_cycles** | Time spent on computation: `wall_cycles - comm_cycles` |
| **exposed_comm_cycles** | Communication time that could not be overlapped with computation — the "pure overhead" |
| **comm_fraction** | Ratio of communication to total time: `comm_cycles / wall_cycles` |
| **ALL_REDUCE** | Collective operation that reduces (e.g., sums) data across all NPUs and broadcasts the result back |
| **ALL_GATHER** | Collective that gathers data from all NPUs so each has the complete result |
| **REDUCE_SCATTER** | Collective that reduces data and scatters different parts to different NPUs |
| **ALL_TO_ALL** | Collective where each NPU sends a different piece of data to every other NPU |
| **Topology** | The interconnect structure connecting NPUs: Ring, FullyConnected, or Switch |
| **Ring** | Bidirectional ring topology — each NPU connects to two neighbors |
| **FullyConnected** | All-to-all topology — every NPU has a direct link to every other |
| **Switch** | Star topology — all NPUs connect through a central switch |
| **.et trace** | Chakra Execution Trace file (protobuf format) representing one NPU's computation graph |
| **Chakra** | MLCommons graph format library for representing AI workload traces |
| **STG** | Symbolic Tensor Graph — generates computation/communication graphs for LLM training workloads |
| **ASTRA-sim** | Distributed training simulator that models network communication and execution timing |
| **Congestion Unaware** | Analytical backend that does not model network congestion (faster, less accurate) |
| **Congestion Aware** | Analytical backend that models network congestion (slower, more accurate) |
| **GQA (Grouped Query Attention)** | Attention variant where multiple query heads share a single KV head (kvhead < head) |
| **Activation Recompute** | Memory optimization that recomputes activations during backward pass instead of storing them |
| **Weight Sharding** | Distributing model weight storage across TP ranks to reduce per-NPU memory |
| **Mixed Precision** | Training with lower precision (FP16/BF16) for speed while maintaining accuracy with FP32 master weights |
| **Micro-batch** | Subdivision of a mini-batch for pipeline parallelism; each micro-batch flows through pipeline stages |
| **Collective** | A communication pattern where multiple NPUs participate (as opposed to point-to-point) |
| **SSE** | Server-Sent Events — HTTP-based protocol for server-to-client event streaming |
