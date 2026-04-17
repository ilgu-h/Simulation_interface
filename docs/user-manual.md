# Simulation Interface — User Manual

> Dashboard that orchestrates **STG → Chakra → ASTRA-sim** to simulate LLM training on configurable distributed hardware.

---

## Table of Contents

1. [Installation & Setup](#1-installation--setup)
2. [Quick Start — First Simulation in 5 Minutes](#2-quick-start--first-simulation-in-5-minutes)
3. [Web Interface Guide](#3-web-interface-guide)
4. [Workload Management](#4-workload-management)
5. [System Configuration](#5-system-configuration)
   - 5.5. [ns-3 Packet-Level Backend](#55-ns-3-packet-level-backend)
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

#### Opting into the ns-3 packet-level backend

The default bootstrap only builds the analytical backend. To additionally build ns-3 (packet-level simulation with congestion control):

```bash
ENABLE_NS3=1 bash scripts/bootstrap.sh
```

This adds three steps on top of the default flow:

1. Clones the ns-3 submodule at `extern/network_backend/ns-3`
2. Installs `libopenmpi-dev` + `openmpi-bin` via `apt` (requires sudo)
3. Builds the `AstraSim_NS3` binary and symlinks it to a stable registry path

ns-3 runs are 10–100× slower than analytical but model packets, queues, ECN marking, and congestion control accurately. See [Section 5.5](#55-ns-3-packet-level-backend) for when to use it and how to configure it.

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
8. Click **"Configure System →"** in the result panel — this carries your workload context forward

### Step 3: Configure the system
1. You arrive at the **System** page with a blue **workload context banner** showing **4 NPUs (DP=2 × TP=2)**
2. The NPU count and expected NPU cross-check are auto-filled from your workload
3. Keep the defaults: **Ring** topology, **50 GB/s** bandwidth, **500 ns** latency
4. Verify the topology SVG preview shows 4 nodes in a ring
5. Click **"Materialize configs"** to write the config files
6. Click **"Continue to Validate →"** in the green success box

### Step 4: Validate and run
1. You arrive at the **Validate** page with your workload prefix pre-filled
2. Check the summary cards: Traces (4), NPUs (4, green match), Binary (ready)
3. Verify the green **"Pre-flight OK"** banner appears
4. Click **"Start run →"**

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
A table of available workloads grouped by trace prefix. Individual `.et` files (one per NPU) are aggregated into workload groups:

| Column | Description |
|--------|-------------|
| (radio) | Select this workload for use in validation |
| Source | `examples` or `run` |
| Workload | Trace prefix name (e.g., `microbenchmarks/reduce_scatter/4npus_1MB/reduce_scatter`) |
| Traces | Number of `.et` files in this workload group (one per NPU) |
| Total size | Combined size of all trace files |

Click a row or its radio button to select a workload, then click **"Continue to Validate →"** to navigate to the Validate page with the workload pre-filled.

Workload sources:
- **examples**: bundled microbenchmarks in `frameworks/astra-sim/examples/workload/`
- **run**: traces from previous workload generation runs

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
9. **Result panel**: shows run_id, list of generated trace files, stdout output. After successful generation, a **"Configure System →"** button appears with a context summary (e.g., "Next: configure system for 4 NPUs (DP=2 × TP=2 × SP=1 × PP=1)"). Clicking it navigates to the System page with workload context pre-filled via URL parameters.

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
- **Workload context banner** (conditional): when arriving from the Workload page via "Configure System →", a blue banner shows the parallelism dimensions (e.g., "**4 NPUs** — DP=2 × TP=2 × SP=1 × PP=1") and the workload prefix. The network NPU count and "Expected NPU count" cross-check are auto-filled to match. The banner is dismissible with ×. When accessing the page directly (no URL params), no banner appears and the page works as before.
- **Backend picker**: dropdown selecting the simulation backend (Analytical Congestion Unaware, Analytical Congestion Aware, or ns-3). Shows "built" or "needs build" status. When **ns-3** is selected, the Network section is replaced by the ns-3 advanced configuration panel (see [Section 5.5](#55-ns-3-packet-level-backend)) — logical dimensions, an "Essentials" card with the most-used knobs, and nine collapsed accordions for the full ~42-field surface.
- **Network section**: multi-dimensional topology editor
  - Each dimension row has: topology type (Ring/FullyConnected/Switch), NPU count, bandwidth (GB/s), latency (ns), delete button
  - **"+ add dim"** button adds a new dimension with defaults (Ring, 2 NPUs, 50 GB/s, 500 ns)
  - Total NPUs = product of all dimension NPU counts
- **System section**: scheduling policy (LIFO/FIFO), endpoint-delay, active-chunks-per-dimension, preferred-dataset-splits, local-mem-bw, boost-mode, four collective implementation fields, collective-optimization
- **Memory section**: remote memory architecture type selector with conditional fields (see [Section 5.3](#53-memory-configuration))
- **Materialize button**: writes config files to disk (creates a run directory). Disabled when validation errors exist.

#### Right column — Preview & validation
- **Topology SVG**: live visualization of the network topology (Ring, FullyConnected, or Switch)
- **Issue list**: validation errors (red), warnings (amber), and info (gray) from real-time validation
- **Materialized output**: green success box with run_id, file paths, and a **"Continue to Validate →"** button that navigates to the Validate page with the workload prefix pre-filled

### 3.5 Validate & Run (`/validate`)

Pre-flight checks and simulation launch:

#### Left column
- **Workload prefix input**: text input with quick-select buttons for available trace prefixes. The workload is pre-filled when navigating from the Workload page ("Continue to Validate →") or the System page ("Continue to Validate →") via the `?workload=` URL parameter.
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
- **Progress bar** (ns-3 runs): a `finished / total NPUs` indicator with a horizontal fill bar appears whenever a `progress` event arrives. ns-3 runs can be minutes long; the bar lets you see forward motion between the occasional log bursts. During stretches of silence the event stream also emits a heartbeat every 30 seconds so the run never looks indistinguishable from a hang.

### 3.7 Results (`/results/[id]`)

Six tabs for analyzing simulation output, plus two ns-3-only tabs that appear automatically when the run used the ns-3 backend:

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
- Click **"Download timeline.json"** to save the Chrome Tracing JSON file (the backend sends a `Content-Disposition: attachment` header to force download)
- Open the downloaded file at [ui.perfetto.dev](https://ui.perfetto.dev) or `chrome://tracing`
- Shows compute and communication bands per NPU, plus collective instant markers
- Note: timestamps are approximate (analytical backend doesn't emit per-collective timing)

#### Logs tab
Each log file has an **"open"** link that opens the file in a new browser tab for inline viewing:
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

#### Links tab (ns-3 runs only)
Packet-level communication stats derived from ns-3's `fct.txt` output:

- **Heatmap matrix**: rows = source nodes, columns = destination nodes. Cell color intensity encodes total bytes for that `(src, dst)` flow pair — hot links stand out at a glance. Hover a cell for the full tooltip (flow count, bytes, avg/max FCT).
- **Top-10 pairs table**: the ten hottest `src → dst` pairs by total bytes, with flow count, byte volume, and FCT statistics per pair.

Useful for spotting hotspot links, validating that your parallelism layout matches the physical topology, and comparing how different congestion-control modes redistribute load.

#### Config tab (ns-3 runs only)
Inline view of the exact `config.txt` ns-3 ran with, plus a **Download** button. This is the file ns-3 read at launch — typed schema fields, `extra_overrides`, ECN maps, and output-path redirects all already applied. Use it for:

- Reproducing a run (feed the downloaded file as a base config for a future run)
- Verifying overrides (check that a UI change actually reached the simulator)
- Diffing two runs' physical parameters when comparing cycles

Analytical runs don't have this tab — they use `network.yml` which is already visible via `/results/<id>/spec`.

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

ASTRA-sim supports four remote memory architecture types:

| Type | Description |
|------|-------------|
| **NO_MEMORY_EXPANSION** | No remote memory access (default). No additional fields needed. |
| **PER_NODE_MEMORY_EXPANSION** | Each node has dedicated remote memory. Transactions are serialized per node. |
| **PER_NPU_MEMORY_EXPANSION** | Each NPU has independent remote memory access. No serialization. |
| **MEMORY_POOL** | Single shared memory pool across all NPUs. Transactions are serialized globally. |

#### Common fields (for all expansion types)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `remote-mem-latency` | int | 0 | Remote memory access latency in **nanoseconds** |
| `remote-mem-bw` | int | 0 | Remote memory bandwidth in **GB/s** (must be > 0 for expansion types) |

#### PER_NODE_MEMORY_EXPANSION additional fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `num-nodes` | int | — | Number of nodes (must be ≥ 1) |
| `num-npus-per-node` | int | — | NPUs per node (must be ≥ 1) |

#### Memory runtime model

For all expansion types, the remote memory access time is calculated as:
```
runtime = remote-mem-latency + (tensor_size / remote-mem-bw)
```

#### Example configurations

**No expansion** (default):
```json
{ "memory-type": "NO_MEMORY_EXPANSION" }
```

**Per-node expansion** (4 nodes, 8 NPUs each):
```json
{
  "memory-type": "PER_NODE_MEMORY_EXPANSION",
  "remote-mem-latency": 100,
  "remote-mem-bw": 50,
  "num-nodes": 4,
  "num-npus-per-node": 8
}
```

**Memory pool** (shared):
```json
{
  "memory-type": "MEMORY_POOL",
  "remote-mem-latency": 200,
  "remote-mem-bw": 100
}
```

#### UI behavior

In the System page, selecting a memory type other than **No memory expansion** reveals the latency and bandwidth fields. Selecting **Per-node expansion** additionally reveals the `num-nodes` and `npus-per-node` fields. Switching back to a simpler type clears the irrelevant fields automatically.

### 5.4 Backend Selection

| Backend | Description | Typical runtime |
|---------|-------------|-----------------|
| **Analytical Congestion Unaware** (`analytical_cu`) | Fast analytical model — no congestion modeling. Best for quick iteration. | ms–seconds |
| **Analytical Congestion Aware** (`analytical_ca`) | Analytical model with congestion approximation — more accurate but slower. | seconds |
| **ns-3** (`ns3`) | Packet-level network simulation with real queues, ECN marking, and congestion-control algorithms (DCQCN, HPCC, TIMELY, DCTCP, PINT). Opt-in: requires `ENABLE_NS3=1 bash scripts/bootstrap.sh`. See [Section 5.5](#55-ns-3-packet-level-backend) for configuration. | minutes–hours |

**When to pick ns-3** over analytical:
- You need per-link utilization, flow-completion-time distributions, or queue-depth data — analytical models summarize these away.
- You're evaluating a congestion-control algorithm (HPCC vs DCQCN vs DCTCP).
- You've narrowed down a workload configuration with analytical and want high-fidelity numbers before making hardware decisions.

For everything else — topology sweeps, parallelism trade-off exploration, quick sanity checks — analytical is the right default.

### 5.5 ns-3 Packet-Level Backend

The ns-3 backend turns every hop into a real packet-level simulation: link queues fill and drain, RED/ECN marks packets, congestion-control algorithms react to feedback, and flow completion times reflect actual contention. In exchange for 10–100× the runtime of analytical, you get per-link utilization, queue occupancy samples, PFC pause events, and per-flow FCT data — the raw material for hardware-validation studies.

This section assumes you've already run `ENABLE_NS3=1 bash scripts/bootstrap.sh` (see [Section 1.2](#12-running-bootstrapsh)).

#### 5.5.1 Three levels of configuration

The UI layers ns-3's ~42 knobs into three tiers of complexity so casual users see a short form while hardware engineers can drill into every parameter:

| Tier | What's shown | Who it's for |
|------|-------------|--------------|
| **Top-level** | Logical dimensions, physical topology path, base mix-config path | Everyone — these three fields define the network shape. |
| **Essentials card** (always open) | `CC_MODE`, `PACKET_PAYLOAD_SIZE`, `BUFFER_SIZE`, `ERROR_RATE_PER_LINK`, `ENABLE_QCN`, `RATE_AI`, `RATE_HAI`, `MIN_RATE` | Typical users tuning congestion control and buffer size. |
| **Nine collapsed accordions** | The remaining ~34 fields grouped by function | Hardware engineers running CC-algorithm comparisons or rate-sensitivity sweeps. |

Every knob has a sensible default drawn from the shipped reference `config.txt`, so you only need to touch the fields you actually care about.

#### 5.5.2 Logical vs physical topology

ns-3 splits the network into two orthogonal concerns, and the UI reflects that split:

- **Logical topology** (`logical_dims`): how NPUs are grouped into collective dimensions. Same semantics as the analytical backend's `npus_count`. For example, `[8]` = one 8-NPU ring; `[4, 2]` = 4 rings of 2 NPUs each.
- **Physical topology** (`physical_topology_path`): a path to a text file describing switches, hosts, and per-link bandwidth/latency. ns-3 reads this file at startup — the format is documented in the file itself (one topology per row). The default points at `extern/network_backend/ns-3/scratch/topology/8_nodes_1_switch_topology.txt` (8 hosts, 1 switch, 400 Gbps per host link). Change the path to swap topologies without rebuilding.

> **Why the split?** Analytical backends compute collective timing directly from dimension sizes. ns-3 needs real hops, so it takes a separate file describing them. You can run the same logical workload on different physical topologies to see how topology choice affects completion time.

#### 5.5.3 Essentials card — quick reference

| Field | Default | Role |
|-------|---------|------|
| `CC_MODE` | 12 (HPCC-PINT-HAI) | Congestion-control algorithm. See table below. |
| `PACKET_PAYLOAD_SIZE` | 1000 | Bytes per packet (64–9216; jumbo frames up to 9216). |
| `BUFFER_SIZE` | 32 | Switch per-port buffer in MB (1–1024). |
| `ERROR_RATE_PER_LINK` | 0.0 | Random packet-loss probability per hop (0.0–1.0). Leave at 0 for a clean-link baseline. |
| `ENABLE_QCN` | true | Turn on RDMA congestion notification. Required for DCQCN/HPCC to do anything. |
| `RATE_AI` | 50Mb/s | Additive-increase rate (DCQCN). |
| `RATE_HAI` | 100Mb/s | Hyper-additive-increase rate (DCQCN fast recovery). |
| `MIN_RATE` | 100Mb/s | Floor for pacing. |

Rate strings use ns-3's format: `<number><unit>` where unit is `Mb/s`, `Gb/s`, `Tb/s`, etc.

#### 5.5.4 Congestion-control mode reference

| Value | Mode | Status | Notes |
|------:|------|--------|-------|
| 1 | **DCQCN** | Implemented | Default RoCE congestion control. Reacts to ECN marks with AI/MD. |
| 3 | **HPCC** | Implemented | High-Precision Congestion Control. Uses INT (in-band network telemetry) for sub-RTT reaction. |
| 7 | **TIMELY** | Implemented | RTT-based pacing. |
| 8 | **DCTCP** | Implemented | TCP-style ECN reaction, adapted for RDMA. |
| 10 | **PINT** | Implemented | Probabilistic INT variant. |
| 11 | **HPCC-PINT** | Experimental | In upstream defaults but `rdma-hw.cc` has no dedicated path — silently falls through to a default algorithm. UI shows an amber warning. |
| 12 | **HPCC-PINT-HAI** | Experimental | Same caveat as 11. Shipped as the default to match upstream config.txt. |

**If you see the amber warning** — the run will complete, but cycle counts won't reflect the mode name. Pick 3 (HPCC) or 1 (DCQCN) for trustworthy numbers.

#### 5.5.5 The nine accordions

Everything else lives in collapsed accordions. Each one is grouped by function, so if you know which axis you want to tune you can go straight to it:

| Accordion | Fields | When to touch |
|-----------|--------|---------------|
| **Rates** | `RATE_AI`, `RATE_HAI`, `MIN_RATE`, `DCTCP_RATE_AI` | Tuning DCQCN / DCTCP aggressiveness. |
| **Congestion control tuning** | `ALPHA_RESUME_INTERVAL`, `RATE_DECREASE_INTERVAL`, `RP_TIMER`, `EWMA_GAIN`, `FAST_RECOVERY_TIMES`, `CLAMP_TARGET_RATE` | DCQCN timer/gain sensitivity studies. |
| **Window / HPCC advanced** | `HAS_WIN`, `GLOBAL_T`, `VAR_WIN`, `FAST_REACT`, `U_TARGET`, `MI_THRESH`, `INT_MULTI`, `PINT_LOG_BASE`, `PINT_PROB`, `MULTI_RATE`, `SAMPLE_FEEDBACK`, `RATE_BOUND` | HPCC/PINT utilization-target and window-control tuning. |
| **ECN threshold maps** | `KMAX_MAP`, `KMIN_MAP`, `PMAX_MAP` | Per-bandwidth ECN marking thresholds — see next subsection. |
| **Global switches** | `USE_DYNAMIC_PFC_THRESHOLD`, `ENABLE_TRACE`, `ACK_HIGH_PRIO`, `L2_BACK_TO_ZERO` | Turning features on/off for ablation studies. |
| **Packet / link layer** | `L2_CHUNK_SIZE`, `L2_ACK_INTERVAL`, `NIC_TOTAL_PAUSE_TIME` | MTU-level and ACK-coalescing experiments. |
| **Timing** | `SIMULATOR_STOP_TIME`, `QLEN_MON_START`, `QLEN_MON_END` | Bound the simulated time window. Picoseconds. |
| **Link control** | `LINK_DOWN` (src, dst, time) | Fault-injection: drop a link at simulator time T. |
| **Raw overrides** | `extra_overrides` key-value table | Escape hatch — see below. |

#### 5.5.6 ECN threshold maps

Three maps configure RED/ECN marking per link speed:

- `KMIN_MAP` — below this queue depth, never mark.
- `KMAX_MAP` — above this queue depth, always mark.
- `PMAX_MAP` — marking probability between KMIN and KMAX.

Each map has one row per bandwidth tier. The defaults cover 25G/40G/100G/200G/400G/2.4T. **All three maps must have the same row count and matching `bandwidth_bps` values per row**; `KMIN.threshold ≤ KMAX.threshold` per row. The schema rejects broken maps at validation time so a misconfigured ECN curve never reaches the simulator.

Edit all three in the **ECN threshold maps** accordion.

#### 5.5.7 Escape hatch — raw overrides

Any key that isn't modeled as a typed field can be set via the **Raw overrides** accordion. Keys are raw `UPPER_SNAKE_CASE` (matching the `config.txt` format) and values are free text. This is applied **last** — after typed fields, after ECN maps — so a raw override wins over a typed value for the same key.

When to use it:
- A new ns-3 build adds a config key we haven't surfaced as a typed field yet.
- You want to test a parameter value outside the typed-field validator's bounds.
- You want a quick one-off without editing code.

When not to use it:
- You want the override to persist — typed fields round-trip through presets; raw overrides don't survive serialization in the same way.

#### 5.5.8 Per-run `config.txt`

Every ns-3 run materializes its full configuration to `runs/<id>/configs/config.txt` before launch. This file is:

- The exact parameter set ns-3 read from disk — typed fields, ECN maps, extra_overrides, and internal path redirects all already applied.
- Available in the UI via the **Config** tab on the results page (inline view + download).
- Available on disk for scripted reproduction: copy it to `extern/network_backend/ns-3/scratch/config/` and set `mix_config_path` to that location for a future run.

Use it when cycles differ unexpectedly between two supposedly-identical runs — diff the two config.txt files and the real parameter difference becomes obvious.

#### 5.5.9 Output files

ns-3 writes four output files per run, all redirected into `runs/<id>/logs/` so concurrent runs don't clobber each other:

| File | Format | Content |
|------|--------|---------|
| `fct.txt` | Plain text, one row per flow | `sip dip sport dport size_bytes start_ns fct_ns standalone_fct_ns`. The Links tab aggregates this into the heatmap. |
| `qlen.txt` | Plain text, space-separated | Switch-port queue depth samples at simulator ticks. Sparse — only logged when ≥1000 bytes are queued. |
| `pfc.txt` | Plain text | PFC pause/resume events. Empty for workloads that don't saturate links. |
| `mix.tr` | ns-3 binary trace | Full packet-level trace. Not parsed by the UI today; reserved for `ns-3`-native tools. |

The Links tab (Section 3.7) consumes `fct.txt`; the Config tab surfaces `config.txt`. For anything more detailed, open the files directly.

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
| Memory bandwidth | error | `remote-mem-bw` must be > 0 for memory expansion types |
| Per-node fields | error | `num-nodes` and `num-npus-per-node` must be ≥ 1 for PER_NODE_MEMORY_EXPANSION |

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
| **Remote Memory Expansion** | Simulated remote memory subsystem that models off-chip or off-node memory access with configurable latency and bandwidth |
| **PER_NODE_MEMORY_EXPANSION** | Memory architecture where each node has dedicated remote memory; transactions within a node are serialized |
| **PER_NPU_MEMORY_EXPANSION** | Memory architecture where each NPU has independent remote memory access with no serialization |
| **MEMORY_POOL** | Shared memory pool architecture where all NPUs share one memory with globally serialized transactions |
| **SSE** | Server-Sent Events — HTTP-based protocol for server-to-client event streaming |
| **ns-3** | Discrete-event network simulator (nsnam.org) — provides the packet-level backend with real queues and congestion control |
| **CC_MODE** | ns-3 congestion-control mode selector: 1=DCQCN, 3=HPCC, 7=TIMELY, 8=DCTCP, 10=PINT, 11/12=experimental HPCC-PINT variants |
| **DCQCN** | Data Center Quantized Congestion Notification — RoCE-v2 congestion control using ECN marks with additive-increase/multiplicative-decrease |
| **HPCC** | High-Precision Congestion Control — uses in-band telemetry (INT) for sub-RTT rate adjustment |
| **DCTCP** | Data Center TCP — ECN-aware congestion control adapted for low-latency datacenter fabrics |
| **TIMELY** | RTT-based datacenter congestion control |
| **PINT** | Probabilistic INT — a sampled variant of HPCC's in-band telemetry |
| **PFC** | Priority Flow Control — per-priority link-level pause frames that stop traffic when a downstream queue fills |
| **ECN** | Explicit Congestion Notification — IP-level bit marking used instead of dropping packets when queues get deep |
| **QCN** | Quantized Congestion Notification — the IEEE 802.1Qau-based ECN scheme used by RDMA |
| **FCT** | Flow Completion Time — time from first byte to last byte of a flow; a primary ns-3 output metric |
| **QLEN** | Queue length — switch-port buffer occupancy; ns-3 samples this during the `QLEN_MON_START`–`QLEN_MON_END` window |
| **INT** | In-band Network Telemetry — switches embed per-hop bandwidth/queue data in packets for end-host congestion control |
| **MTU / L2 chunk** | Maximum transmission unit; `L2_CHUNK_SIZE` in ns-3's config sets the link-layer chunk size |
| **Logical topology** | (ns-3) NPU grouping for collective operations — same concept as analytical's `npus_count` |
| **Physical topology** | (ns-3) A separate topology file describing switches, hosts, and per-link bandwidth/latency that ns-3 reads at startup |
| **extra_overrides** | Escape-hatch dictionary in ns-3 config: raw `UPPER_SNAKE_CASE` keys overlaid last, winning over typed fields |
