"""Run lifecycle routes.

- POST /runs/validate          unified pre-flight (Phase 3)
- POST /runs                   start a run (materialize → build → simulate)
- GET  /runs/{id}              status snapshot
- GET  /runs/{id}/events       SSE stream of log lines + status
- POST /runs/{id}/cancel       SIGTERM a live run
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.api.system import ConfigBundle
from app.build.backend_adapter import get_backend, is_built
from app.orchestrator import astra_runner, pipeline
from app.storage.fs_layout import new_run_id, run_dir, traces_dir
from app.storage.registry import Run, get_engine

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[3]
ASTRA_SIM_DIR = REPO_ROOT / "frameworks" / "astra-sim"
EXAMPLES_WORKLOAD_DIR = ASTRA_SIM_DIR / "examples" / "workload"

# 4-NPU reduce_scatter microbenchmark — smoke-run target.
SMOKE_WORKLOAD_PREFIX = (
    EXAMPLES_WORKLOAD_DIR / "microbenchmarks" / "reduce_scatter" / "4npus_1MB" / "reduce_scatter"
)
SMOKE_NPUS = 4

_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _assert_safe_id(run_id: str) -> None:
    if not _SAFE_ID_RE.match(run_id):
        raise HTTPException(400, f"Invalid id: {run_id!r}")

# Native collective implementations recognised by the analytical backend.
# Anything else is allowed (custom collectives) but warned on.
KNOWN_COLLECTIVES = {
    "ring",
    "direct",
    "halvingDoubling",
    "doubleBinaryTree",
    "oneRing",
    "oneDirect",
}


class WorkloadRef(BaseModel):
    """Either point at an existing trace prefix or a previously generated run."""

    kind: Literal["existing", "run"]
    # For kind="existing": absolute or repo-relative prefix (no .et).
    # For kind="run":      run_id; we look in runs/<id>/traces/workload.*.et.
    value: str
    # For kind="run", optional override of the basename (default "workload").
    name: str = "workload"


class RunValidateRequest(BaseModel):
    workload: WorkloadRef
    bundle: ConfigBundle
    smoke_run: bool = False


class Issue(BaseModel):
    severity: Literal["error", "warning", "info"]
    field: str
    message: str


class WorkloadSummary(BaseModel):
    prefix: str
    trace_count: int
    total_size_bytes: int


class SmokeRunResult(BaseModel):
    ran: bool
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_sec: float | None = None


class RunValidateResponse(BaseModel):
    ok: bool
    issues: list[Issue]
    workload: WorkloadSummary | None
    binary_present: bool
    smoke: SmokeRunResult | None = None
    estimated_run_seconds: float | None = Field(
        None,
        description="Crude estimate based on total trace size; not authoritative.",
    )


def _validate_comm_group(workload_prefix: Path) -> list[Issue]:
    """Inspect the sibling {prefix}.json that STG emits for comm-group IDs.

    Missing file -> warn; a workload that never references a group is fine.
    Malformed/empty JSON when .et traces exist -> error, because ASTRA-sim
    would silently clear all groups and then crash on the first node that
    references one (e.g. `communicator group N not found`).
    """
    path = workload_prefix.parent / f"{workload_prefix.name}.json"
    if not path.exists():
        return [
            Issue(
                severity="warning",
                field="workload.comm_group",
                message=(
                    f"No comm-group file at {path.name}. ASTRA-sim will run "
                    "with no groups (fine for single-dim workloads)."
                ),
            )
        ]
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Issue(
                severity="error",
                field="workload.comm_group",
                message=f"Failed to parse {path.name}: {exc}",
            )
        ]
    if not isinstance(payload, dict) or not payload:
        return [
            Issue(
                severity="error",
                field="workload.comm_group",
                message=f"{path.name} is empty; multi-dim workloads will crash.",
            )
        ]
    return []


def _resolve_workload(ref: WorkloadRef) -> tuple[Path, list[Path]]:
    """Return (prefix, sorted list of .et files matching prefix.*.et)."""
    if ref.kind == "run":
        _assert_safe_id(ref.value)
        prefix = traces_dir(ref.value) / ref.name
    else:
        raw = Path(ref.value)
        prefix = raw if raw.is_absolute() else (REPO_ROOT / raw)
        prefix = pipeline.assert_repo_path(prefix)
    matches = sorted(prefix.parent.glob(f"{prefix.name}.*.et"))
    return prefix, matches


def _validate(req: RunValidateRequest) -> RunValidateResponse:
    issues: list[Issue] = []
    prefix, traces = _resolve_workload(req.workload)
    workload_summary: WorkloadSummary | None = None

    if not traces:
        issues.append(
            Issue(
                severity="error",
                field="workload",
                message=f"No .et files found at prefix {prefix}.*.et",
            )
        )
    else:
        total = sum(p.stat().st_size for p in traces)
        workload_summary = WorkloadSummary(
            prefix=str(prefix), trace_count=len(traces), total_size_bytes=total
        )
        # NPU consistency
        net_npus = req.bundle.network.total_npus
        if len(traces) != net_npus:
            issues.append(
                Issue(
                    severity="error",
                    field="workload/network",
                    message=(
                        f"Workload has {len(traces)} .et traces but network "
                        f"prod(npus_count)={net_npus}. They must match."
                    ),
                )
            )
        # Comm-group configuration sanity (see astra-sim Workload.cc).
        issues.extend(_validate_comm_group(prefix))

    # Backend binary check
    binary_present = False
    try:
        adapter = get_backend(req.bundle.backend)
    except KeyError as e:
        issues.append(Issue(severity="error", field="backend", message=str(e)))
        adapter = None

    if adapter is not None:
        binary_present = is_built(adapter)
        if not binary_present:
            issues.append(
                Issue(
                    severity="warning",
                    field="backend",
                    message=(
                        f"Binary {adapter.binary_path} not built. Phase 4 will "
                        "auto-build at run time, but a manual check via "
                        "`bash scripts/build_backends.sh analytical` is recommended."
                    ),
                )
            )

    # Collective implementation sanity (warn-only — custom names are valid).
    sys_cfg = req.bundle.system
    for fname, impls in (
        ("all-reduce-implementation", sys_cfg.all_reduce_implementation),
        ("all-gather-implementation", sys_cfg.all_gather_implementation),
        ("reduce-scatter-implementation", sys_cfg.reduce_scatter_implementation),
        ("all-to-all-implementation", sys_cfg.all_to_all_implementation),
    ):
        if not impls:
            issues.append(
                Issue(
                    severity="error",
                    field=f"system.{fname}",
                    message="Collective implementation list must not be empty.",
                )
            )
            continue
        for impl in impls:
            if impl.startswith("custom-"):
                continue  # opaque to analytical backend; flagged via build hook in Phase 4
            if impl not in KNOWN_COLLECTIVES:
                issues.append(
                    Issue(
                        severity="warning",
                        field=f"system.{fname}",
                        message=(
                            f"'{impl}' is not in the recognised native collective set "
                            f"({sorted(KNOWN_COLLECTIVES)}). May fail at runtime."
                        ),
                    )
                )

    # Inherit cross-field checks from /configs/validate (Switch>=2 etc).
    from app.api.system import _validate_bundle

    bundle_issues, _ = _validate_bundle(req.bundle)
    issues.extend(bundle_issues)

    has_error = any(i.severity == "error" for i in issues)

    estimated = None
    if workload_summary:
        # Very rough heuristic: 5 µs per kilobyte of trace, capped at 60 s.
        est = (workload_summary.total_size_bytes / 1024.0) * 5e-6
        estimated = min(est, 60.0)

    smoke: SmokeRunResult | None = None
    if req.smoke_run and not has_error and adapter is not None and binary_present:
        smoke = _smoke_run(adapter)
        if smoke.returncode != 0:
            issues.append(
                Issue(
                    severity="error",
                    field="smoke_run",
                    message=(
                        f"Smoke run failed (returncode={smoke.returncode}). "
                        "Inspect stderr_tail for the runtime error."
                    ),
                )
            )
            has_error = True

    return RunValidateResponse(
        ok=not has_error,
        issues=issues,
        workload=workload_summary,
        binary_present=binary_present,
        smoke=smoke,
        estimated_run_seconds=estimated,
    )


def _smoke_run(adapter) -> SmokeRunResult:
    """Run ASTRA-sim against the bundled 4-NPU reduce_scatter microbenchmark.

    Uses the bundled reference system/network/memory configs to isolate
    failures from the user's bundle — the goal is to confirm the binary
    runs end-to-end on a known-good input.
    """
    import time

    sys_ref = ASTRA_SIM_DIR / "examples" / "system" / "native_collectives" / "Ring_4chunks.json"
    net_ref = ASTRA_SIM_DIR / "examples" / "network" / "analytical" / "Ring_4npus.yml"
    mem_ref = (
        ASTRA_SIM_DIR / "examples" / "remote_memory" / "analytical" / "no_memory_expansion.json"
    )

    cmd = [
        str(adapter.binary_path),
        f"--workload-configuration={SMOKE_WORKLOAD_PREFIX}",
        f"--system-configuration={sys_ref}",
        f"--remote-memory-configuration={mem_ref}",
        f"--network-configuration={net_ref}",
    ]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    duration = time.time() - t0
    return SmokeRunResult(
        ran=True,
        returncode=proc.returncode,
        stdout_tail=proc.stdout[-1500:],
        stderr_tail=proc.stderr[-1500:],
        duration_sec=duration,
    )


@router.post("/validate", response_model=RunValidateResponse)
def validate_run(req: RunValidateRequest) -> RunValidateResponse:
    return _validate(req)


# ===== Phase 4: start / status / events / cancel ============================


class StartRunRequest(BaseModel):
    workload: WorkloadRef
    bundle: ConfigBundle


class StartRunResponse(BaseModel):
    run_id: str
    status: str


class RunStatus(BaseModel):
    run_id: str
    status: str
    config_dir: str | None = None
    log_dir: str | None = None


class RunListItem(BaseModel):
    run_id: str
    status: str
    created_at: str


@router.get("", response_model=list[RunListItem])
def list_runs() -> list[RunListItem]:
    """List all runs, most recent first."""
    from sqlmodel import select

    with Session(get_engine()) as session:
        rows = session.exec(select(Run).order_by(Run.created_at.desc())).all()  # type: ignore[attr-defined]
    return [
        RunListItem(run_id=r.id, status=r.status, created_at=r.created_at.isoformat())
        for r in rows
    ]


@router.post("", response_model=StartRunResponse)
def start_run(req: StartRunRequest) -> StartRunResponse:
    # Resolve workload prefix the same way validate does, but reject paths
    # that escape the repo root.
    prefix, traces = _resolve_workload(req.workload)
    if not traces:
        raise HTTPException(400, f"No .et files at {prefix}.*.et")
    safe_prefix = pipeline.assert_repo_path(prefix)

    # NPU consistency hard-gate (do not start a run we already know will fail).
    expected = req.bundle.network.total_npus
    if len(traces) != expected:
        raise HTTPException(
            400,
            f"Workload has {len(traces)} traces but network expects {expected}.",
        )

    run_id = new_run_id()
    pipeline._set_status(run_id, "queued")
    pipeline.execute_pipeline_async(run_id, req.bundle, safe_prefix)
    return StartRunResponse(run_id=run_id, status="queued")


@router.get("/{run_id}", response_model=RunStatus)
def get_run(run_id: str) -> RunStatus:
    _assert_safe_id(run_id)
    with Session(get_engine()) as session:
        row = session.get(Run, run_id)
    if row is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return RunStatus(
        run_id=run_id,
        status=row.status,
        config_dir=str(run_dir(run_id) / "configs"),
        log_dir=str(run_dir(run_id) / "logs"),
    )


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str) -> dict[str, bool]:
    _assert_safe_id(run_id)
    ok = astra_runner.cancel_run(run_id)
    if ok:
        pipeline.append_event(run_id, "log", text="[cancel] SIGTERM sent")
    return {"signalled": ok}


@router.get("/{run_id}/events")
async def stream_events(run_id: str) -> StreamingResponse:
    """SSE stream that tails runs/<id>/logs/events.log.

    Replays the file from the start (so a refresh shows full history),
    then tails new lines until a `done` event lands or the file goes
    untouched for too long.
    """
    _assert_safe_id(run_id)
    log_path = pipeline.events_log(run_id)

    async def gen():
        # Wait briefly for the file to appear if the run just started.
        for _ in range(50):
            if log_path.exists():
                break
            await asyncio.sleep(0.1)
        if not log_path.exists():
            yield _sse({"kind": "error", "text": f"events log {log_path} missing"})
            return

        offset = 0
        idle_since = time.time()
        last_done_seen = False
        while True:
            try:
                with log_path.open("r") as f:
                    f.seek(offset)
                    chunk = f.read()
                    offset = f.tell()
            except FileNotFoundError:
                break
            if chunk:
                idle_since = time.time()
                for line in chunk.splitlines():
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    yield _sse(rec)
                    if rec.get("kind") == "done":
                        last_done_seen = True
            if last_done_seen:
                # Give the client a beat to receive the final event.
                await asyncio.sleep(0.2)
                return
            # 5 min of silence with no `done` → assume the writer crashed.
            if time.time() - idle_since > 300:
                yield _sse({"kind": "error", "text": "stream idle 5 min, closing"})
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
