# Simulation Interface — Implementation Plan

> **Audience.** A future Claude Code session picking this project up. Read this file first, then execute phases in order. Each phase lists concrete files, commands, and acceptance criteria so you can work without re-researching the frameworks.

---

## 1. Context

We are building a dashboard-style interface that orchestrates three existing frameworks to simulate LLM training/serving on configurable distributed hardware:

| Framework | Role | Repo | Language |
|---|---|---|---|
| **STG** (Symbolic Tensor Graph) | Generates per-NPU Chakra execution traces from model + parallelism specs | https://github.com/astra-sim/symbolic_tensor_graph | Python |
| **Chakra** | Standard execution-trace IR; converters, visualizers, timeline tools | https://github.com/mlcommons/chakra | Python |
| **ASTRA-sim** | Consumes `.et` traces + system/network/memory configs → per-component stats | https://github.com/ilgu-h/astra-sim (fork of astra-sim/astra-sim) | C++ |

**Pipeline:**

```
User (dashboard) → STG (generate .et) → Chakra (validate/visualize) → ASTRA-sim (simulate) → per-NPU stats
```

**Goal.** One UI where the user can (a) select or generate a workload, (b) configure system/network/memory, (c) pick a model and parallelism strategy, (d) validate the config, (e) run the simulation with auto-build, (f) drill into per-component results. It must stay flexible — new topologies, collective impls, backends, and models add cleanly.

**Scope confirmed with user.**
- Full end-to-end pipeline (Phases 0–5) for the first milestone.
- Single-user local tool (SQLite + filesystem, localhost, no auth).
- Git submodules pinned to commits (convert to forks only when modifying).
- Frontend: Next.js 14 + React + Tailwind + shadcn/ui.
- Backend: FastAPI + Pydantic v2 + SQLModel.

---

## 2. Framework Facts (distilled — do NOT re-research)

### 2.1 ASTRA-sim

**Binary paths after build** (`bash frameworks/astra-sim/build/astra_analytical/build.sh`):
- `frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware`
- `frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Aware`
- Other backends (ns3, garnet, htsim) under `frameworks/astra-sim/build/astra_{ns3,garnet,htsim}/`.

**CLI template:**
```bash
./AstraSim_Analytical_Congestion_Unaware \
  --workload-configuration=<path without .et extension> \
  --system-configuration=<system.json> \
  --remote-memory-configuration=<memory.json> \
  --network-configuration=<network.yml> \
  --logging-folder=<log_dir> \
  --num-queues-per-dim=1 \
  --comm-scale=1.0 \
  --injection-scale=1.0 \
  --rendezvous-protocol=false
```

**System config (JSON) — key fields:**
`scheduling-policy` (LIFO/FIFO), `endpoint-delay`, `active-chunks-per-dimension`, `preferred-dataset-splits`, `all-reduce-implementation` (list), `all-gather-implementation`, `reduce-scatter-implementation`, `all-to-all-implementation`, `collective-optimization` (localBWAware/""), `local-mem-bw`, `boost-mode`, `roofline-enabled`, `peak-perf`, and optional `*-custom` suffixed lists for custom collectives.

**Network config (YAML, analytical backend):**
```yaml
topology: [ Ring | Mesh2D | FullyConnected | Switch ]
npus_count: [ 4 | 8 | 16 | ... ]
bandwidth: [ 50.0 ]    # GB/s per dim
latency:   [ 500.0 ]   # ns per dim
```

**Remote memory (JSON):** `{ "memory-type": "NO_MEMORY_EXPANSION" }` minimal form.

**Reference configs** live under `frameworks/astra-sim/examples/{system,network,remote_memory,workload}/` — use as seed presets.

### 2.2 Chakra

**Install:** `pip install -e frameworks/chakra`

**CLI tools** (6): `chakra_converter`, `chakra_trace_link`, `chakra_visualizer`, `chakra_timeline_visualizer`, `chakra_generator`, `chakra_jsonizer`.

**ET protobuf schema** (`frameworks/chakra/schema/protobuf/et_def.proto`): `Node { id, name, type (COMP_NODE | COMM_SEND_NODE | COMM_RECV_NODE | COMM_COLL_NODE | MEM_LOAD/STORE | METADATA), ctrl_deps, data_deps, start_time_micros, duration_micros, inputs, outputs, attr }`. Collective types: ALL_REDUCE, REDUCE, ALL_GATHER, GATHER, SCATTER, BROADCAST, ALL_TO_ALL, REDUCE_SCATTER, REDUCE_SCATTER_BLOCK, BARRIER.

**Visualizer output formats:** PDF, DOT, GraphML (prefer GraphML for large traces).

**Dashboard use:** run `chakra_visualizer` on STG output for preview/validation; `chakra_timeline_visualizer` produces Chrome Tracing JSON that Perfetto can render.

### 2.3 STG

**Entry:** `python frameworks/symbolic_tensor_graph/main.py`

**CLI args:** `--output_dir`, `--output_name` (supports `%d` substitution per NPU), `--model_type` (`llama`/`dense`/`gpt`/`moe`/`debug`), `--batch`, `--seq`, `--dmodel`, `--head`, `--num_stacks`, `--ff_dim`, `--vocab`, `--dp`, `--tp`, `--pp`, `--sp`, `--ep`, `--weight_sharded`, `--activation_recompute`, `--mixed_precision`.

**Total NPUs = DP × TP × PP × SP.**

**Outputs:** per-NPU `<name>.0.et`, `<name>.1.et`, ... + `comm_group_config.json`.

**Deps:** separate conda env (see `frameworks/symbolic_tensor_graph/environment.yml`), Python 3.12, sympy, protobuf. Does NOT need PyTorch or Chakra installed.

**No built-in model presets.** Dashboard owns the preset library.

---

## 3. Repo Layout (target)

```
Simulation_interface/
├── plan.md                         # this file
├── README.md
├── .gitmodules
├── frameworks/                     # submodules (pin commits)
│   ├── astra-sim/                  # https://github.com/ilgu-h/astra-sim
│   ├── chakra/                     # https://github.com/mlcommons/chakra
│   └── symbolic_tensor_graph/      # https://github.com/astra-sim/symbolic_tensor_graph
├── backend/
│   ├── app/
│   │   ├── api/                    # FastAPI routes
│   │   │   ├── workload.py
│   │   │   ├── system.py
│   │   │   ├── runs.py
│   │   │   └── results.py
│   │   ├── schemas/                # Pydantic v2 models
│   │   │   ├── stg_spec.py
│   │   │   ├── system_config.py
│   │   │   ├── network_config.py
│   │   │   ├── memory_config.py
│   │   │   ├── run_spec.py
│   │   │   └── presets/            # model preset JSONs (GPT-3, LLaMA-7B, etc.)
│   │   ├── orchestrator/
│   │   │   ├── stg_runner.py       # subprocess wrapper for STG
│   │   │   ├── chakra_tools.py     # wrappers for chakra_* CLIs
│   │   │   ├── astra_runner.py     # subprocess wrapper for ASTRA-sim binary
│   │   │   └── pipeline.py         # end-to-end run driver
│   │   ├── build/
│   │   │   └── backend_adapter.py  # registry: backend name → binary path + build cmd
│   │   ├── parsers/
│   │   │   └── astra_logs.py       # log folder → parquet stats
│   │   └── storage/
│   │       ├── registry.py         # SQLModel tables: Run, Artifact, Preset
│   │       └── fs_layout.py        # runs/<id>/ path helpers
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── smoke/                  # reproduces examples/run_scripts/*
│   └── pyproject.toml
├── frontend/
│   ├── app/                        # Next.js app router
│   │   ├── workload/page.tsx
│   │   ├── system/page.tsx
│   │   ├── model/page.tsx
│   │   ├── validate/page.tsx
│   │   ├── run/[id]/page.tsx
│   │   └── results/[id]/page.tsx
│   ├── components/
│   │   ├── forms/                  # schema-driven forms
│   │   ├── topology/               # react-flow topology viz
│   │   └── charts/                 # recharts wrappers
│   └── lib/
│       ├── api.ts                  # generated from OpenAPI
│       └── schemas.ts              # mirrored types
├── runs/                           # gitignored, per-run artifacts
│   └── <run_id>/
│       ├── spec.json               # full RunSpec
│       ├── configs/                # generated system.json, network.yml, memory.json
│       ├── traces/                 # *.et + comm_group_config.json
│       ├── logs/                   # ASTRA-sim log output + stdout.log
│       └── stats.parquet           # parsed per-NPU stats
├── scripts/
│   ├── bootstrap.sh                # init submodules, envs, build backends
│   ├── build_backends.sh           # (re)build ASTRA-sim backends
│   └── new_run.sh                  # helper for CLI-driven runs
├── docker/
│   └── builder.Dockerfile          # CMake + protobuf + conda for reproducible builds
├── docker-compose.yml
├── TASKS.md                        # shared task board for cowork (see §5)
└── .github/
    └── workflows/ci.yml            # lint + smoke tests
```

---

## 4. Phased Build Plan

**Per phase:** each phase lists goal, files to create/modify, acceptance criteria, and the cowork role split (see §5).

### Phase 0 — Bootstrap

**Goal.** Repo skeleton, submodules wired, envs built, health-check endpoints up.

**Tasks.**
1. Add submodules:
   ```bash
   git submodule add https://github.com/ilgu-h/astra-sim frameworks/astra-sim
   git submodule add https://github.com/mlcommons/chakra frameworks/chakra
   git submodule add https://github.com/astra-sim/symbolic_tensor_graph frameworks/symbolic_tensor_graph
   git submodule update --init --recursive
   ```
2. Write `scripts/bootstrap.sh`:
   - Create conda env `stg-env` from `frameworks/symbolic_tensor_graph/environment.yml`.
   - Create Python venv `.venv-backend` and `pip install -e frameworks/chakra` + backend deps.
   - `bash frameworks/astra-sim/build/astra_analytical/build.sh` for both congestion variants.
3. `docker/builder.Dockerfile` + `docker-compose.yml` (service `builder` containing all build deps; service `backend` depending on it).
4. Backend skeleton: FastAPI app with `/health` returning `{status: "ok"}`, SQLModel init, empty routers for workload/system/runs/results.
5. Frontend skeleton: Next.js 14 project, shadcn/ui installed, placeholder pages for the six routes, API client stub, Tailwind configured.
6. `.gitignore` for `runs/`, `.venv-backend/`, conda envs, node_modules, `frameworks/astra-sim/build/*/build/`.
7. `.github/workflows/ci.yml`: lint (ruff, eslint), unit tests.

**Acceptance.**
- `bash scripts/bootstrap.sh` exits 0 on clean Ubuntu 22.04.
- `curl localhost:8000/health` → `ok`.
- `AstraSim_Analytical_Congestion_Unaware --help` runs.
- `cd frontend && pnpm dev` renders six empty pages.

---

### Phase 1 — Workload Interface (STG + existing `.et` picker)

**Goal.** User can (a) browse existing `.et` files, (b) generate new ones via STG.

**Tasks.**
1. `backend/app/schemas/stg_spec.py` — Pydantic `StgSpec` mirroring STG CLI args with validators:
   - `num_stacks > 0`, `dmodel % head == 0`, warn if `dp*tp*pp*sp` conflicts with declared NPU count.
2. `backend/app/orchestrator/stg_runner.py` — subprocess wrapper that activates conda env and calls `main.py`.
3. `backend/app/schemas/presets/` — seed with LLaMA-7B, LLaMA-70B, GPT-3-175B JSON files.
4. Endpoints:
   - `GET /workloads/library` → list of `.et` files under `frameworks/astra-sim/examples/workload/` + user uploads.
   - `POST /workloads/generate` (body: `StgSpec`) → runs STG, returns `run_id` + artifact list.
   - `GET /workloads/presets` → preset library.
5. `backend/app/orchestrator/chakra_tools.py` — wrap `chakra_visualizer` to produce GraphML for preview.
6. Frontend: `app/workload/page.tsx` — two tabs ("Select existing" / "Generate new"), form from `StgSpec` schema, preset picker, preview panel that shows generated file tree and a GraphML viewer for the first trace.

**Acceptance.**
- Generating LLaMA-7B with DP=2, TP=2, PP=2 produces 8 `.et` files in `runs/<id>/traces/`.
- `chakra_visualizer` runs on each without error.
- Preset selection prefills the form.

---

### Phase 2 — System / Network / Memory Configuration

**Goal.** Three linked forms produce the three ASTRA-sim config files. Topology builder renders the current selection. Backend selector switches which ASTRA-sim binary will run.

**Tasks.**
1. Pydantic schemas matching §2.1: `SystemConfig`, `NetworkConfig` (analytical first), `MemoryConfig`.
2. `backend/app/build/backend_adapter.py` — registry keyed by backend name → `{binary_path, build_cmd, network_schema}`. Start with `analytical_cu` and `analytical_ca`.
3. Cross-field validator: `prod(NetworkConfig.npus_count) == total_npus_from_stg_spec`.
4. `POST /configs/validate` → returns issues list.
5. `POST /configs/materialize` → writes files to `runs/<id>/configs/`.
6. Frontend:
   - `app/system/page.tsx` — form sections for scheduling, collectives, memory, compute.
   - `components/topology/` — react-flow renderer that takes `NetworkConfig` and draws nodes/links; color-codes validation errors.
   - Backend selector dropdown populated from `/backends`.

**Acceptance.**
- For Ring-8, Mesh2D-16, FullyConnected-4 topologies, generated YAML files diff-equal reference files in `frameworks/astra-sim/examples/network/analytical/`.
- Topology viz updates live as NPU counts change.

---

### Phase 3 — Validation Interface

**Goal.** Unified pre-flight check before any run.

**Tasks.**
1. `POST /runs/validate` that aggregates: schema validity, NPU-count consistency, trace/system match, binary existence, any missing build artifacts.
2. Smoke-run mode: optionally run ASTRA-sim on a 4-NPU microbenchmark trace with the selected system config to catch runtime config errors early.
3. Frontend `app/validate/page.tsx`: summary cards (topology diagram, model summary, parallelism breakdown, estimated run time from trace size), issue list with severities (error blocks, warning proceeds).

**Acceptance.**
- All three reference runs from `frameworks/astra-sim/examples/run_scripts/` pass validation when configured through the UI.
- Intentionally broken configs (NPU mismatch, unknown collective impl) produce clear error messages.

---

### Phase 4 — Run Interface with Auto-build

**Goal.** One click runs the whole pipeline; logs stream live; artifacts are persisted per run.

**Tasks.**
1. `backend/app/orchestrator/pipeline.py`:
   - Materialize configs.
   - If binary missing or older than submodule HEAD, call `scripts/build_backends.sh <backend>`.
   - If custom collectives declared in `SystemConfig.*-custom`, rebuild with the custom sources included.
   - Launch ASTRA-sim; stream stdout via SSE; persist to `runs/<id>/logs/stdout.log`.
   - Update run record in SQLite: `queued → building → running → succeeded|failed`.
2. `POST /runs` starts a run, `GET /runs/{id}` polls, `GET /runs/{id}/events` is an SSE stream.
3. Cancel = kill subprocess + mark run as cancelled.
4. Frontend `app/run/[id]/page.tsx`: status header, live log pane (ansi-to-html), cancel button, link to results when done.

**Acceptance.**
- 4-NPU ring all-reduce microbenchmark from examples runs end-to-end through the UI.
- Deleting the binary and re-running triggers a rebuild automatically.

---

### Phase 5 — Results Interface

**Goal.** Per-component drill-down and comparison view.

**Tasks.**
1. `backend/app/parsers/astra_logs.py` — parse ASTRA-sim log folder into a tidy schema and write `stats.parquet`:
   - per-NPU: compute_us, comm_us, mem_us, idle_us, total_us
   - per-collective: type, size_bytes, algorithm, start_us, finish_us, src, dst
   - per-layer (when derivable from trace METADATA nodes)
2. `GET /runs/{id}/stats?view=per_npu|per_collective|per_layer`.
3. Timeline: produce Chrome Tracing JSON via `chakra_timeline_visualizer`; host it at a static URL and embed Perfetto UI via iframe.
4. Frontend `app/results/[id]/page.tsx`:
   - Summary card (end-to-end time, slowest NPU, top 3 collectives).
   - Tabs: Per-NPU, Per-Collective, Timeline, Topology heatmap (reuse react-flow with link utilization coloring), Raw logs.
   - Comparison mode: `?compare=<other_run_id>` overlays stats and highlights config diff.

**Acceptance.**
- For the microbenchmark, stats match what `examples/run_scripts/` produces when run by hand (cycle-count-level agreement).
- Timeline renders in Perfetto.
- Comparison view clearly surfaces which config field changed and the resulting delta in stats.

---

### Phase 6 — Flexibility Layer (absorbed across phases)

Already captured as part of earlier phases:
- **Backend adapter registry** (Phase 2) for adding new ASTRA-sim backends.
- **Preset JSONs** (Phase 1) for adding model shapes.
- **Custom collective paths** (Phase 4) via rebuild hook.
- **Run spec export** (Phase 5) — `GET /runs/{id}/spec.yaml` for reproducibility.

---

## 5. Cowork Procedure (Planner → Executor → Reviewer → Tester)

Derived from `/home/ilgu-hong/Desktop/claude_cowork_workaround.txt`. Purpose: split work across multiple Claude sessions safely on a single Linux host.

### 5.1 Roles

| Role | Session | Model | Permission | Responsibility |
|---|---|---|---|---|
| **Planner** | Terminal 1 (lead, `tmux new -s lead`) | Opus | interactive | Breaks phase into tasks, writes rows into `TASKS.md`, merges branches, resolves conflicts. |
| **Executor(s)** | Terminal 2..N (workers) in **separate git worktrees** | Sonnet | interactive or `-p` | Claim a task row, implement in their worktree branch, push, open a PR. |
| **Reviewer** | Agent call (`subagent_type: code-reviewer` or `security-reviewer`) invoked by Planner after PR opens | Sonnet | Plan mode (read-only) | Leaves structured review; blocks on CRITICAL issues per the global `code-review` rule. |
| **Tester** | Headless `claude -p` or `subagent_type: tdd-guide` | Sonnet | default | Writes/extends tests per `testing.md` 80%+ coverage rule, runs smoke suite, attaches results to PR. |

### 5.2 Shared Artifacts

- **`TASKS.md`** — the one source of truth for in-flight work. Rows look like:
  ```
  | id   | phase | title                         | owner   | branch             | status      | pr  |
  |------|-------|-------------------------------|---------|--------------------|-------------|-----|
  | T-07 | P2    | NetworkConfig pydantic schema | worker1 | feat/network-cfg   | in_review   | #12 |
  ```
  Atomic claim/update guarded by `flock`:
  ```bash
  flock -x TASKS.md -c "python scripts/update_task.py T-07 status in_review"
  ```
- **`runs/` directory** — shared read; each executor writes only under its own `runs/<run_id>/`.
- **Git worktrees** — one per executor per feature. Convention: `../Simulation_interface-<branch>`.
- **Logs** — per-agent `logs/<role>-<session>.log` for observability.

### 5.3 Standard Flow (per task)

1. **Planner**
   - Picks a task from this plan's phase.
   - Appends row to `TASKS.md` with status `todo`.
   - Optionally creates the worktree + branch for the worker:
     ```bash
     git worktree add ../Simulation_interface-feat-network-cfg feat/network-cfg
     ```
2. **Executor**
   - In its worktree terminal:
     ```bash
     cd ../Simulation_interface-feat-network-cfg
     claude
     ```
   - Claims row in `TASKS.md` (`status: in_progress`, `owner: <name>`).
   - Invokes `superpowers:test-driven-development` skill, writes failing test, implements, makes it pass.
   - Commits, pushes, opens PR, updates row to `status: in_review`.
3. **Reviewer** (triggered by Planner)
   - Planner dispatches `Agent { subagent_type: "code-reviewer", prompt: "Review PR #12 against plan.md §4.Phase-2 and rules/common/code-review.md" }` and a parallel `security-reviewer` agent if the diff touches auth/input boundaries.
   - Review comments posted to PR. CRITICAL → block; HIGH → request changes; MEDIUM/LOW → inline nit.
4. **Tester**
   - Planner dispatches `Agent { subagent_type: "tdd-guide", prompt: "Verify coverage ≥80% for PR #12 and run backend/tests/smoke/" }`.
   - Tester updates row to `tests_passed: true/false` and attaches coverage numbers.
5. **Merge**
   - Planner merges only when Reviewer approves AND Tester passes. Worktree is removed; row moved to `done`.

### 5.4 Launch Commands (copy-paste-ready)

**Lead session.**
```bash
tmux new -s lead
claude --model opus
```

**Executor spawn (from lead, for parallel work).** Use the in-session parallelism pattern:
```
Agent { subagent_type: "general-purpose", isolation: "worktree", prompt: "... task T-07 ..." }
```
Call multiple `Agent` tools in one message to dispatch in parallel, one per independent task.

**Headless executor** (for batch/automation):
```bash
claude -p "/execute-plan plan.md --task T-07" \
  --output-format stream-json \
  > logs/executor-T-07.log
```

**Reviewer on demand:**
```bash
claude -p "Review PR #12 per plan.md and rules/common/code-review.md" \
  --permission-mode plan \
  > logs/reviewer-PR-12.log
```

**Tester on demand:**
```bash
claude -p "/test-coverage backend/ and run backend/tests/smoke/" \
  > logs/tester-PR-12.log
```

### 5.5 Safety Rules (inherited from the cowork guide)

- Never `--dangerously-skip-permissions`. Restrict per-agent tools via `allowedTools`.
- Any shared-file write uses `flock`.
- Two agents must **never** edit the same file without separate worktrees.
- Resource-cap long runners:
  ```bash
  systemd-run --user --scope -p MemoryMax=6G -p CPUQuota=300% claude -p "..."
  ```
- Prompt cache TTL is 5 min; batch worker invocations to stay warm.

### 5.6 Handoffs to Existing Skills

- `superpowers:dispatching-parallel-agents` — use before any parallel fan-out.
- `superpowers:using-git-worktrees` — use whenever creating an executor.
- `superpowers:test-driven-development` — executor uses this during implementation.
- `superpowers:requesting-code-review` — planner uses this at PR time.
- `claude-devfleet` — optional upgrade path if manual orchestration becomes tedious.

---

## 6. Verification (End-to-End)

Each item below must pass before the project is called "working":

1. `bash scripts/bootstrap.sh` succeeds on a clean machine.
2. Generate LLaMA-7B trace via UI (DP=2, TP=2, PP=2) → 8 `.et` files appear under `runs/<id>/traces/`.
3. Build a Ring-8 analytical config via UI → generated `network.yml` diffs clean against `frameworks/astra-sim/examples/network/analytical/Ring_8npus.yml` (allowing whitespace).
4. Run the 4-NPU ring all-reduce microbenchmark end-to-end via UI → `runs/<id>/stats.parquet` exists and end-to-end time matches `examples/run_scripts/` reference within 1% tolerance.
5. Results page renders per-NPU timing, topology heatmap, and Perfetto timeline.
6. Add a stub new ASTRA-sim backend by dropping a new `BackendAdapter` entry — it appears in the UI dropdown without frontend changes.
7. Cowork dry-run: Planner opens T-01, spawns worker in worktree, worker PRs, reviewer+tester approve, Planner merges. TASKS.md transitions through all statuses cleanly.
8. Smoke test CI workflow (`.github/workflows/ci.yml`) reproduces the three reference runs from `examples/run_scripts/` through the API.

---

## 7. Quick Reference for Future Claude Sessions

- **Where am I in the plan?** Check `TASKS.md` for in-flight rows and `git log --oneline` for what's landed.
- **What should I do next?** Pick the lowest-numbered `todo` row in `TASKS.md`, follow §5.3.
- **Where are the framework facts?** §2 of this file — do not re-research unless the phase explicitly asks for it.
- **How do I run a simulation by hand?** Follow §2.1 CLI template against materialized configs under `runs/<id>/configs/`.
- **What skills should I invoke?** §5.6 lists the handoffs.
- **Which rules apply?** Global rules under `~/.claude/rules/common/` — particularly `coding-style.md`, `testing.md`, `code-review.md`, `security.md`. Web rules (`~/.claude/rules/web/`) apply to `frontend/`.
