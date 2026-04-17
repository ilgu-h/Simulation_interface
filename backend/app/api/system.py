"""System / network / memory config routes (Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.build.backend_adapter import BackendAdapter, is_built, list_backends
from app.schemas.memory_config import MemoryConfig
from app.schemas.network_config import (
    AnalyticalNetworkConfig,
    NetworkConfigUnion,
    NS3NetworkConfig,
)
from app.schemas.system_config import SystemConfig
from app.storage.fs_layout import configs_dir, new_run_id

router = APIRouter()


class ConfigBundle(BaseModel):
    backend: str = "analytical_cu"
    system: SystemConfig = SystemConfig()
    network: NetworkConfigUnion = Field(default_factory=AnalyticalNetworkConfig)
    memory: MemoryConfig = MemoryConfig()
    expected_npus: int | None = None  # cross-check: network.total_npus == this


class Issue(BaseModel):
    severity: str  # error|warning|info
    field: str
    message: str


class ValidateResponse(BaseModel):
    ok: bool
    issues: list[Issue]
    total_npus: int
    binary_present: bool


class MaterializeResponse(BaseModel):
    run_id: str
    config_dir: str
    files: dict[str, str]  # kind -> absolute path


def _validate_bundle(bundle: ConfigBundle) -> tuple[list[Issue], BackendAdapter | None]:
    issues: list[Issue] = []
    adapter: BackendAdapter | None = None

    try:
        adapter = next(b for b in list_backends() if b.name == bundle.backend)
    except StopIteration:
        issues.append(
            Issue(severity="error", field="backend", message=f"Unknown backend '{bundle.backend}'.")
        )

    if adapter and not is_built(adapter):
        issues.append(
            Issue(
                severity="warning",
                field="backend",
                message=(
                    f"Binary {adapter.binary_path} not built yet. "
                    "Will be auto-built when a run starts (Phase 4)."
                ),
            )
        )

    if bundle.expected_npus is not None and bundle.network.total_npus != bundle.expected_npus:
        field_name = (
            "network.npus_count"
            if isinstance(bundle.network, AnalyticalNetworkConfig)
            else "network.logical_dims"
        )
        issues.append(
            Issue(
                severity="error",
                field=field_name,
                message=(
                    f"total_npus={bundle.network.total_npus} but workload expects "
                    f"{bundle.expected_npus} NPUs."
                ),
            )
        )

    if isinstance(bundle.network, AnalyticalNetworkConfig):
        # Switch topology only sensible at the outermost dim with >=2 NPUs.
        for i, t in enumerate(bundle.network.topology):
            if t == "Switch" and bundle.network.npus_count[i] < 2:
                issues.append(
                    Issue(
                        severity="error",
                        field=f"network.npus_count[{i}]",
                        message="Switch topology requires npus_count >= 2.",
                    )
                )
    elif isinstance(bundle.network, NS3NetworkConfig):
        # ns-3 physical topology lives inside the ns-3 submodule; warn (not
        # error) if the file is missing so users can edit configs before the
        # submodule is cloned.
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[3]
        for field, rel in (
            ("network.physical_topology_path", bundle.network.physical_topology_path),
            ("network.mix_config_path", bundle.network.mix_config_path),
        ):
            candidate = repo_root / "frameworks" / "astra-sim" / rel
            if not candidate.exists():
                issues.append(
                    Issue(
                        severity="warning",
                        field=field,
                        message=(
                            f"{rel} not found under astra-sim. Either run "
                            "'ENABLE_NS3=1 bash scripts/bootstrap.sh' to clone the "
                            "ns-3 submodule, or update the path."
                        ),
                    )
                )

    # Memory config validation.
    mem = bundle.memory
    if mem.memory_type != "NO_MEMORY_EXPANSION":
        if mem.remote_mem_bw <= 0:
            issues.append(
                Issue(
                    severity="error",
                    field="memory.remote-mem-bw",
                    message="remote-mem-bw must be > 0 for memory expansion.",
                )
            )
    if mem.memory_type == "PER_NODE_MEMORY_EXPANSION":
        if not mem.num_nodes or mem.num_nodes < 1:
            issues.append(
                Issue(
                    severity="error",
                    field="memory.num-nodes",
                    message="num-nodes must be >= 1 for PER_NODE_MEMORY_EXPANSION.",
                )
            )
        if not mem.num_npus_per_node or mem.num_npus_per_node < 1:
            issues.append(
                Issue(
                    severity="error",
                    field="memory.num-npus-per-node",
                    message="num-npus-per-node must be >= 1 for PER_NODE_MEMORY_EXPANSION.",
                )
            )

    return issues, adapter


@router.post("/validate", response_model=ValidateResponse)
def validate_configs(bundle: ConfigBundle) -> ValidateResponse:
    issues, adapter = _validate_bundle(bundle)
    has_error = any(i.severity == "error" for i in issues)
    return ValidateResponse(
        ok=not has_error,
        issues=issues,
        total_npus=bundle.network.total_npus,
        binary_present=bool(adapter and is_built(adapter)),
    )


@router.post("/materialize", response_model=MaterializeResponse)
def materialize_configs(bundle: ConfigBundle) -> MaterializeResponse:
    issues, _ = _validate_bundle(bundle)
    blocking = [i for i in issues if i.severity == "error"]
    if blocking:
        raise HTTPException(status_code=400, detail=[i.model_dump() for i in blocking])

    run_id = new_run_id()
    cdir = configs_dir(run_id)
    cdir.mkdir(parents=True, exist_ok=True)

    system_path = cdir / "system.json"
    memory_path = cdir / "memory.json"
    system_path.write_text(json.dumps(bundle.system.to_json_dict(), indent=4) + "\n")
    memory_path.write_text(json.dumps(bundle.memory.to_json_dict(), indent=4) + "\n")

    # Variant-specific network materialization. Analytical → network.yml;
    # ns3 → logical_topology.json (physical topology stays inside ns-3).
    if isinstance(bundle.network, AnalyticalNetworkConfig):
        network_path = cdir / "network.yml"
        network_path.write_text(bundle.network.to_yaml())
    else:  # NS3NetworkConfig
        network_path = cdir / "logical_topology.json"
        network_path.write_text(bundle.network.to_logical_topology_json())

    return MaterializeResponse(
        run_id=run_id,
        config_dir=str(cdir),
        files={
            "network": str(network_path),
            "system": str(system_path),
            "memory": str(memory_path),
        },
    )


# Quick way to surface schema problems instead of the generic 422 wall.
@router.post("/dryrun")
def dryrun_bundle(payload: dict) -> dict:
    try:
        bundle = ConfigBundle.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    return {
        "ok": True,
        "total_npus": bundle.network.total_npus,
        "backend": bundle.backend,
    }


# /backends lives outside the /configs prefix — re-exported via main.py.
backends_router = APIRouter()


class BackendInfo(BaseModel):
    name: str
    label: str
    network_schema: str
    binary_path: str
    built: bool


@backends_router.get("/backends", response_model=list[BackendInfo])
def get_backends() -> list[BackendInfo]:
    out: list[BackendInfo] = []
    for b in list_backends():
        out.append(
            BackendInfo(
                name=b.name,
                label=b.label,
                network_schema=b.network_schema,
                binary_path=str(b.binary_path),
                built=is_built(b),
            )
        )
    return out


def _path_unused(_p: Path) -> None: ...
