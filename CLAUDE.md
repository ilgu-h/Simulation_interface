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

## Testing

- `tests/unit/` — schemas, parsers, adapter (pure functions, no I/O)
- `tests/integration/` — API endpoints via httpx ASGITransport
- `tests/smoke/` — actually runs ASTRA-sim; `skipif` binary not built
- Coverage target: 80%+. Current: 81%.
- `backend/conftest.py` sets `SIM_RUNS_DIR` to tmpdir before any module import.

## What's NOT done

- Cowork harness (TASKS.md + worktrees): deferred.
- Embedded Perfetto iframe: timeline.json is downloadable, not embedded.
- Per-layer breakdown: requires METADATA nodes in .et traces (none in current microbenchmarks).
- Topology heatmap with link utilization: needs per-link stats not emitted by analytical backend.
