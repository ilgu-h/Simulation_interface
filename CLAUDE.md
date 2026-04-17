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

- **Separate config file:** ns-3 uses `config.txt` (plain-text key-value, not YAML) for its physical topology; it lives inside the ns-3 submodule (`extern/network_backend/ns-3/scratch/config/config.txt`). The UI lets users edit the path but not the file contents — physical topology editing happens in-place.
- **Logical vs physical split:** the UI's `logical_dims` array feeds `--logical-topology-configuration` (a small JSON); `--network-configuration` points at the ns-3 `config.txt`. Analytical uses a single `network.yml` for both concerns.
- **cwd matters:** the ns-3 binary expects to run from `ns-3/build/scratch/` so that `config.txt`'s relative paths (`../../scratch/topology/...`) resolve. The orchestrator sets this automatically.
- **CLI flag differences:** ns-3 accepts `--logical-topology-configuration` (analytical doesn't) and rejects `--logging-folder` (analytical requires it). `AstraInvocation.emit_logging_folder` toggles this.

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
