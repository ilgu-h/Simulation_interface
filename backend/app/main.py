"""FastAPI entrypoint.

Phase 0 surface area: only `/health`. Routers for workload/system/runs/results
are registered with no endpoints yet so URL prefixes are reserved.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import results, runs, system, workload
from app.storage.registry import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Simulation Interface API",
        version="0.0.1",
        lifespan=lifespan,
    )

    # Frontend dev server runs on localhost:3000 by default.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(workload.router, prefix="/workloads", tags=["workloads"])
    app.include_router(system.router, prefix="/configs", tags=["configs"])
    app.include_router(runs.router, prefix="/runs", tags=["runs"])
    app.include_router(results.router, prefix="/results", tags=["results"])

    return app


app = create_app()
