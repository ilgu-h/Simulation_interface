"""Workload routes (Phase 1).

Endpoints
- GET  /workloads/library         existing .et files (examples + uploads)
- GET  /workloads/presets         model preset library
- POST /workloads/generate        run STG to create new traces
- GET  /workloads/preview/{run_id}/{npu_idx}.graphml   chakra_visualizer output
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.orchestrator.chakra_tools import visualize_trace
from app.orchestrator.stg_runner import run_stg
from app.schemas.stg_spec import StgSpec
from app.storage.fs_layout import new_run_id, previews_dir, run_dir, traces_dir
from app.storage.registry import Artifact, Run, get_engine

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_WORKLOAD_DIR = REPO_ROOT / "frameworks" / "astra-sim" / "examples" / "workload"
PRESETS_DIR = REPO_ROOT / "backend" / "app" / "schemas" / "presets"


class LibraryEntry(BaseModel):
    source: str  # "examples" | "run"
    run_id: str | None = None
    name: str
    path: str
    size_bytes: int


class GenerateResponse(BaseModel):
    run_id: str
    total_npus: int
    trace_files: list[str]
    stdout_tail: str


def _read_presets() -> list[dict[str, Any]]:
    if not PRESETS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(PRESETS_DIR.glob("*.json")):
        out.append(json.loads(p.read_text()))
    return out


@router.get("/library", response_model=list[LibraryEntry])
def list_library() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    if EXAMPLES_WORKLOAD_DIR.exists():
        for p in sorted(EXAMPLES_WORKLOAD_DIR.rglob("*.et")):
            entries.append(
                LibraryEntry(
                    source="examples",
                    name=p.relative_to(EXAMPLES_WORKLOAD_DIR).as_posix(),
                    path=str(p),
                    size_bytes=p.stat().st_size,
                )
            )
    # Also surface traces from completed runs.
    from app.storage.registry import RUNS_DIR

    if RUNS_DIR.exists():
        for run_traces in sorted(RUNS_DIR.glob("*/traces")):
            run_id = run_traces.parent.name
            for p in sorted(run_traces.glob("*.et")):
                entries.append(
                    LibraryEntry(
                        source="run",
                        run_id=run_id,
                        name=p.name,
                        path=str(p),
                        size_bytes=p.stat().st_size,
                    )
                )
    return entries


@router.get("/presets")
def list_presets() -> list[dict[str, Any]]:
    return _read_presets()


@router.post("/generate", response_model=GenerateResponse)
def generate_workload(spec: StgSpec) -> GenerateResponse:
    run_id = new_run_id()
    out_dir = traces_dir(run_id)

    # Persist the spec next to traces for reproducibility.
    run_root = run_dir(run_id)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "spec.json").write_text(spec.model_dump_json(indent=2))

    try:
        result = run_stg(spec, out_dir)
    except (RuntimeError, FileNotFoundError) as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    expected = spec.total_npus
    if len(result.trace_files) != expected:
        raise HTTPException(
            status_code=500,
            detail=(
                f"STG produced {len(result.trace_files)} .et files; "
                f"expected {expected}. stderr:\n{result.stderr[:2000]}"
            ),
        )

    # Record run + artifacts.
    engine = get_engine()
    with Session(engine) as session:
        run = Run(id=run_id, status="succeeded")
        session.add(run)
        for trace in result.trace_files:
            session.add(Artifact(run_id=run_id, kind="trace", path=str(trace)))
        session.add(Artifact(run_id=run_id, kind="spec", path=str(run_root / "spec.json")))
        session.commit()

    return GenerateResponse(
        run_id=run_id,
        total_npus=expected,
        trace_files=[str(p) for p in result.trace_files],
        stdout_tail=result.stdout[-2000:],
    )


@router.get("/preview/{run_id}/{npu_idx}.graphml")
def preview_trace(run_id: str, npu_idx: int) -> FileResponse:
    """Render the per-NPU trace to GraphML on demand and stream it back."""
    et_file = traces_dir(run_id) / f"workload.{npu_idx}.et"
    if not et_file.exists():
        raise HTTPException(status_code=404, detail=f"Trace {et_file} not found.")

    out = previews_dir(run_id) / f"workload.{npu_idx}.graphml"
    if not out.exists():
        try:
            visualize_trace(et_file, out, fmt="graphml")
        except (RuntimeError, FileNotFoundError) as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    return FileResponse(out, media_type="application/xml", filename=out.name)
