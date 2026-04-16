"""Subprocess wrapper around STG's main.py.

We invoke the conda env's interpreter directly (no `conda activate` needed)
so this works from any parent shell, including unactivated FastAPI workers.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.schemas.stg_spec import StgSpec

REPO_ROOT = Path(__file__).resolve().parents[3]
STG_DIR = REPO_ROOT / "frameworks" / "symbolic_tensor_graph"
STG_MAIN = STG_DIR / "main.py"

# `~/miniforge3/envs/stg-env/bin/python` — overridable for non-default installs.
DEFAULT_STG_PYTHON = Path.home() / "miniforge3" / "envs" / "stg-env" / "bin" / "python"


def stg_python() -> Path:
    return Path(os.environ.get("STG_PYTHON", DEFAULT_STG_PYTHON))


@dataclass(frozen=True)
class StgRunResult:
    output_dir: Path
    trace_files: list[Path]
    stdout: str
    stderr: str
    returncode: int


def run_stg(
    spec: StgSpec,
    output_dir: Path,
    output_name: str = "workload",
    *,
    timeout_sec: int = 1800,
) -> StgRunResult:
    """Generate per-NPU .et traces with STG.

    Files land at `<output_dir>/<output_name>.<npu_idx>.et`. Returns the list
    of generated files, ordered by NPU index.
    """

    py = stg_python()
    if not py.exists():
        raise FileNotFoundError(
            f"STG python not found at {py}. Run scripts/bootstrap.sh "
            "or set STG_PYTHON env var."
        )
    if not STG_MAIN.exists():
        raise FileNotFoundError(f"STG main.py not found at {STG_MAIN}.")

    output_dir.mkdir(parents=True, exist_ok=True)
    cli_args = spec.to_cli_args(str(output_dir), output_name)

    proc = subprocess.run(
        [str(py), str(STG_MAIN), *cli_args],
        cwd=str(STG_DIR),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"STG exited with code {proc.returncode}.\n"
            f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
        )

    traces = sorted(
        output_dir.glob(f"{output_name}.*.et"),
        key=lambda p: _et_index(p, output_name),
    )
    return StgRunResult(
        output_dir=output_dir,
        trace_files=traces,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )


def _et_index(path: Path, output_name: str) -> int:
    # workload.7.et → 7
    stem_after_name = path.name[len(output_name) + 1 : -len(".et")]
    try:
        return int(stem_after_name)
    except ValueError:
        return -1
