# Simulation Interface

A dashboard that orchestrates **STG → Chakra → ASTRA-sim** to simulate LLM training/serving on configurable distributed hardware.

> Full design and phase plan: [`plan.md`](./plan.md). This README only covers how to bootstrap and run.

## Status

**Phase 0 — Bootstrap.** Repo skeleton, framework submodules, host build, FastAPI `/health`, Next.js shell.
Phases 1–5 (workload, configs, validation, run, results) are scoped in `plan.md` §4.

## Layout

```
backend/    FastAPI + SQLModel orchestrator
frontend/   Next.js 14 dashboard
frameworks/ git submodules: astra-sim, chakra, symbolic_tensor_graph
scripts/    bootstrap.sh, build_backends.sh
runs/       per-run artifacts (gitignored)
```

## Prerequisites

System packages (Debian/Ubuntu):

```bash
sudo apt install -y git cmake protobuf-compiler curl build-essential
```

You also need Node 20+ with corepack (used to enable pnpm). `bootstrap.sh` will install Miniforge into `~/miniforge3` if conda is not on PATH.

## Bootstrap

```bash
bash scripts/bootstrap.sh
```

Idempotent. Reruns are no-ops once each step's artifact exists. The script:

1. Verifies prerequisites.
2. Initializes the analytical-only sub-submodules of astra-sim (skips ns-3, htsim).
3. Installs Miniforge if missing.
4. Creates the `stg-env` conda environment from `frameworks/symbolic_tensor_graph/environment.yml`.
5. Enables pnpm via `corepack`.
6. Creates `.venv-backend`, installs `frameworks/chakra` (editable) and the backend.
7. Builds the ASTRA-sim analytical backend (CU + CA binaries).

To rebuild ASTRA-sim alone: `FORCE=1 bash scripts/build_backends.sh`.

## Run the dev stack

Two terminals:

```bash
# backend
source .venv-backend/bin/activate
cd backend
uvicorn app.main:app --reload
# → http://localhost:8000/health  →  {"status":"ok"}
```

```bash
# frontend
cd frontend
pnpm install
pnpm dev
# → http://localhost:3000
```

The frontend root page calls the backend `/health` endpoint and shows online/offline.

## Tests

```bash
# backend
source .venv-backend/bin/activate
cd backend && pytest -q

# frontend
cd frontend && pnpm lint && pnpm build
```

## Verifying ASTRA-sim is built

```bash
./frameworks/astra-sim/build/astra_analytical/build/bin/AstraSim_Analytical_Congestion_Unaware --help
```

## What's next

See [`plan.md`](./plan.md) §4 Phase 1 for the workload interface (STG runner + .et picker).
