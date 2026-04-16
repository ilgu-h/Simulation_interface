"""Registry of ASTRA-sim simulation backends.

Adding a new backend = adding one entry. The frontend's backend dropdown
is populated from this registry, so a stub addition here surfaces in the UI
without any frontend change (Phase 6 flexibility).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ASTRA_SIM_DIR = REPO_ROOT / "frameworks" / "astra-sim"


@dataclass(frozen=True)
class BackendAdapter:
    name: str
    label: str
    binary_path: Path
    build_cmd: list[str]
    network_schema: str  # which NetworkConfig variant — "analytical" for now


_REGISTRY: dict[str, BackendAdapter] = {
    "analytical_cu": BackendAdapter(
        name="analytical_cu",
        label="Analytical (Congestion Unaware)",
        binary_path=ASTRA_SIM_DIR
        / "build"
        / "astra_analytical"
        / "build"
        / "bin"
        / "AstraSim_Analytical_Congestion_Unaware",
        build_cmd=["bash", str(REPO_ROOT / "scripts" / "build_backends.sh"), "analytical"],
        network_schema="analytical",
    ),
    "analytical_ca": BackendAdapter(
        name="analytical_ca",
        label="Analytical (Congestion Aware)",
        binary_path=ASTRA_SIM_DIR
        / "build"
        / "astra_analytical"
        / "build"
        / "bin"
        / "AstraSim_Analytical_Congestion_Aware",
        build_cmd=["bash", str(REPO_ROOT / "scripts" / "build_backends.sh"), "analytical"],
        network_schema="analytical",
    ),
}


def list_backends() -> list[BackendAdapter]:
    return list(_REGISTRY.values())


def get_backend(name: str) -> BackendAdapter:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown backend: {name}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def is_built(adapter: BackendAdapter) -> bool:
    return adapter.binary_path.is_file() and adapter.binary_path.stat().st_mode & 0o111 != 0
