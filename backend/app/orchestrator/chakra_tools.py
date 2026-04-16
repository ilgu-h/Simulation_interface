"""Wrappers around the chakra_* CLI tools.

Phase 1 only needs `chakra_visualizer`; later phases will add timeline and
converter wrappers.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

VisualizerFormat = Literal["graphml", "pdf", "dot"]


@dataclass(frozen=True)
class VisualizeResult:
    output_path: Path
    stdout: str
    stderr: str


def _resolve_chakra_visualizer() -> str:
    found = shutil.which("chakra_visualizer")
    if not found:
        raise FileNotFoundError(
            "chakra_visualizer not on PATH. Activate .venv-backend or "
            "re-run scripts/bootstrap.sh."
        )
    return found


def visualize_trace(
    et_file: Path,
    output_path: Path,
    *,
    fmt: VisualizerFormat = "graphml",
    timeout_sec: int = 120,
) -> VisualizeResult:
    """Render a single .et trace to GraphML/PDF/DOT.

    GraphML is the default — `chakra_visualizer --help` recommends it for
    large graphs and it's what the frontend will consume.
    """
    bin_path = _resolve_chakra_visualizer()
    if not et_file.exists():
        raise FileNotFoundError(f"Trace not found: {et_file}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lstrip(".") != fmt:
        output_path = output_path.with_suffix(f".{fmt}")

    proc = subprocess.run(
        [
            bin_path,
            "--input_filename",
            str(et_file),
            "--output_filename",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"chakra_visualizer failed (code {proc.returncode}) for {et_file}.\n"
            f"stderr:\n{proc.stderr}"
        )
    return VisualizeResult(output_path=output_path, stdout=proc.stdout, stderr=proc.stderr)
