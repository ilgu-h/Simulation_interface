"""Run lifecycle routes.

Phase 3 ships /runs/validate (the unified pre-flight check). Phase 4 will
add /runs to start an actual simulation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.system import ConfigBundle
from app.build.backend_adapter import get_backend, is_built
from app.storage.fs_layout import traces_dir

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[3]
ASTRA_SIM_DIR = REPO_ROOT / "frameworks" / "astra-sim"
EXAMPLES_WORKLOAD_DIR = ASTRA_SIM_DIR / "examples" / "workload"

# 4-NPU reduce_scatter microbenchmark — smoke-run target.
SMOKE_WORKLOAD_PREFIX = (
    EXAMPLES_WORKLOAD_DIR / "microbenchmarks" / "reduce_scatter" / "4npus_1MB" / "reduce_scatter"
)
SMOKE_NPUS = 4

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


def _resolve_workload(ref: WorkloadRef) -> tuple[Path, list[Path]]:
    """Return (prefix, sorted list of .et files matching prefix.*.et)."""
    if ref.kind == "run":
        prefix = traces_dir(ref.value) / ref.name
    else:
        raw = Path(ref.value)
        prefix = raw if raw.is_absolute() else (REPO_ROOT / raw)
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
