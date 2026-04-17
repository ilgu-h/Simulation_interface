# Simulation Interface

## What this is

Dashboard that orchestrates **STG → Chakra → ASTRA-sim** to simulate LLM training on configurable distributed hardware. Single-user local tool (SQLite + filesystem, no auth).

## Quick start

```bash
bash scripts/bootstrap.sh          # one-time: submodules, conda, venv, ASTRA-sim build
source .venv-backend/bin/activate
cd backend && uvicorn app.main:app --reload   # http://localhost:8000
cd frontend && pnpm dev                        # http://localhost:3000
```

### ns-3 backend (opt-in)

Default bootstrap builds the analytical backend only. To also build ns-3 (packet-level):

```bash
ENABLE_NS3=1 bash scripts/bootstrap.sh
```

This clones `extern/network_backend/ns-3`, auto-installs `libopenmpi-dev` + `openmpi-bin` (sudo required), and builds the ns-3 backend alongside analytical. The binary gets symlinked to a stable registry path (`frameworks/astra-sim/build/astra_ns3/build/bin/AstraSim_NS3`) so ns-3 version bumps don't ripple into the backend code.

## Architecture

```
backend/   FastAPI (Python 3.11+, Pydantic v2, SQLModel)
frontend/  Next.js 14 (app router, Tailwind, TypeScript strict)
frameworks/  git submodules: astra-sim, chakra, symbolic_tensor_graph
scripts/   bootstrap.sh, build_backends.sh
runs/      per-run artifacts (gitignored)
```

**Pipeline flow:**
User → STG (generate .et) → Chakra (validate/visualize) → ASTRA-sim (simulate) → per-NPU stats

## Key API routes

| Route | Purpose |
|---|---|
| `GET /health` | Readiness probe |
| `GET /workloads/{library,presets}`, `POST /workloads/generate` | Trace management |
| `GET /backends`, `POST /configs/{validate,materialize}` | Config management |
| `POST /runs/validate` | Pre-flight check |
| `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (SSE) | Run lifecycle |
| `GET /results/{id}/{summary,stats,timeline.json,compare}` | Results |

## Commands

```bash
# Backend
cd backend && pytest -q                              # 55 tests
cd backend && pytest --cov=app --cov-report=term      # coverage (81%+)
cd backend && ruff check .                            # lint

# Frontend
cd frontend && pnpm build                             # type-check + build
cd frontend && pnpm lint                              # eslint

# ASTRA-sim
FORCE=1 bash scripts/build_backends.sh                # rebuild
./frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware  # verify
```

## Conventions

- **Hyphenated JSON keys** in system/memory configs use Pydantic aliases (`scheduling_policy` → `scheduling-policy` in JSON via `by_alias=True`).
- **Backend adapter registry** (`backend/app/build/backend_adapter.py`): add a dict entry to surface a new ASTRA-sim backend in the UI.
- **Model presets** (`backend/app/schemas/presets/*.json`): drop a JSON file to add a new preset.
- **Run artifacts** live at `runs/<id>/{spec.json, configs/, traces/, logs/}`.
- **Events log** (`runs/<id>/logs/events.log`): JSONL; SSE endpoint tails this file.

## Vendored patches (re-applied by bootstrap.sh)

1. `frameworks/chakra/setup.cfg` + `setup.py` — stripped for PEP 660 compatibility; protobuf stubs pre-generated via plain `protoc`.
2. `frameworks/astra-sim/extern/helper/cxxopts/cxxopts.hpp` — added `#include <cstdint>` for GCC 13+.
3. STG's conda env gets `pip install tqdm` (missing from environment.yml).
4. **ns-3 only:** `frameworks/astra-sim/extern/network_backend/ns-3/scratch/output/flow.txt` — created with a single `0` line so ns-3's `SetupNetwork()` has something to open. ASTRA-sim-driven runs carry no synthetic flows (traffic comes from workload traces).

## ns-3 backend quirks

- **Separate config file:** ns-3 uses `config.txt` (plain-text key-value, not YAML) for its physical topology and per-link behavior. The shipped base lives at `extern/network_backend/ns-3/scratch/config/config.txt`. The UI exposes ~42 typed fields covering every key in that file; on materialize, the backend parses the base, overlays user overrides, and writes `runs/<id>/configs/config.txt` which is what ns-3 actually reads.
- **Logical vs physical split:** the UI's `logical_dims` array feeds `--logical-topology-configuration` (a small JSON); `--network-configuration` points at the per-run `config.txt`. Analytical uses a single `network.yml` for both concerns.
- **cwd matters:** the ns-3 binary expects to run from `ns-3/build/scratch/` so that `config.txt`'s relative paths (`../../scratch/topology/...`) resolve. The orchestrator sets this automatically. The schema's `physical_topology_path` is project-relative; it gets rewritten to a cwd-relative path when emitted into the per-run `config.txt`.
- **CLI flag differences:** ns-3 accepts `--logical-topology-configuration` (analytical doesn't) and rejects `--logging-folder` (analytical requires it). `AstraInvocation.emit_logging_folder` toggles this.

## ns-3 configuration UI

All ~42 keys from ns-3's `config.txt` are surfaced as typed Pydantic fields on `NS3NetworkConfig` and rendered in the UI via `frontend/components/ns3/Ns3AdvancedSection.tsx`. Layout serves two audiences:

- **Normal users:** see logical dims + an "Essentials" card (CC_MODE, PACKET_PAYLOAD_SIZE, BUFFER_SIZE, ERROR_RATE_PER_LINK, ENABLE_QCN, RATE_AI/HAI/MIN_RATE) open by default.
- **HW engineers:** click into 9 collapsed accordions for the other 34+ knobs (rates, CC tuning, HPCC window, ECN maps, global switches, packet layer, timing, link control, raw overrides).

**CC_MODE enum** (values as accepted by ns-3's `rdma-hw.cc`):

| Value | Name | Status |
|------:|------|--------|
| 1  | DCQCN | implemented |
| 3  | HPCC | implemented |
| 7  | TIMELY | implemented |
| 8  | DCTCP | implemented |
| 10 | PINT | implemented |
| 11 | HPCC-PINT | experimental — no code in rdma-hw.cc |
| 12 | HPCC-PINT-HAI | experimental — no code in rdma-hw.cc |

11 and 12 appear in the shipped default config.txt and upstream docs but the ns-3 parser silently ignores unknown CC_MODE values, so these fall through to a default implementation. The UI shows an amber warning when either is selected. Default schema value is `12` to preserve upstream-compatible behavior.

**Escape hatch:** `extra_overrides: dict[str, str]` on `NS3NetworkConfig` maps to a "Raw overrides" accordion. Keys here are merged after typed fields (so they can even override schema defaults if needed). Use it for future config.txt keys we haven't modeled yet.

**Map validators:** `KMAX_MAP`, `KMIN_MAP`, `PMAX_MAP` must all have the same row count with matching `bandwidth_bps` values per row, and `kmin.threshold <= kmax.threshold`. Enforced at schema level so a broken map never reaches the simulator.

**Per-run config.txt inspection:** `runs/<id>/configs/config.txt` is written for every ns-3 run and preserved in artifacts. Open it to see the exact parameters the simulator ran with — useful for reproducibility and when debugging why two runs produced different cycles.

## Testing

- `tests/unit/` — schemas, parsers, adapter (pure functions, no I/O)
- `tests/integration/` — API endpoints via httpx ASGITransport
- `tests/smoke/` — actually runs ASTRA-sim; `skipif` binary not built
- Coverage target: 80%+. Current: 81%.
- `backend/conftest.py` sets `SIM_RUNS_DIR` to tmpdir before any module import.
- ns-3 smoke test: `tests/smoke/test_ns3_reference_run.py` — skipped unless the ns-3 binary is built locally.

## What's NOT done

- Cowork harness (TASKS.md + worktrees): deferred.
- Embedded Perfetto iframe: timeline.json is downloadable, not embedded.
- Per-layer breakdown: requires METADATA nodes in .et traces (none in current microbenchmarks).
- Topology heatmap with link utilization: needs per-link stats not emitted by analytical backend.
