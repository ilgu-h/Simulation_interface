"""Parse ASTRA-sim's stdout/log.log into per-NPU stats.

The analytical backend currently emits two stats lines per NPU:

    [...] [statistics] [info] sys[N], Wall time: <cycles>
    [...] [statistics] [info] sys[N], Comm time: <cycles>

…and a workload line:

    [...] [workload] [info] sys[N] finished, <cycles> cycles, exposed
    communication <cycles> cycles.

We extract those four fields per NPU, plus a couple of derived ones
(compute = wall − comm, comm_fraction). Other backends will eventually emit
richer stats; the parser is intentionally regex-based so adding fields is
one line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_RE_WALL = re.compile(r"sys\[(\d+)\], Wall time:\s*(\d+)")
_RE_COMM = re.compile(r"sys\[(\d+)\], Comm time:\s*(\d+)")
_RE_FINISHED = re.compile(
    r"sys\[(\d+)\] finished,\s*(\d+) cycles, exposed communication\s*(\d+) cycles"
)


@dataclass(frozen=True)
class NpuStats:
    npu_id: int
    wall_cycles: int
    comm_cycles: int
    exposed_comm_cycles: int

    @property
    def compute_cycles(self) -> int:
        # Coarse: ASTRA-sim analytical doesn't separate compute from idle.
        return max(0, self.wall_cycles - self.comm_cycles)

    @property
    def comm_fraction(self) -> float:
        return (self.comm_cycles / self.wall_cycles) if self.wall_cycles else 0.0


def parse_log_file(log_path: Path) -> list[NpuStats]:
    """Parse one log file and return per-NPU stats sorted by npu_id."""
    text = log_path.read_text() if log_path.exists() else ""
    wall: dict[int, int] = {}
    comm: dict[int, int] = {}
    exposed: dict[int, int] = {}

    for line in text.splitlines():
        if (m := _RE_WALL.search(line)) :
            wall[int(m.group(1))] = int(m.group(2))
        elif (m := _RE_COMM.search(line)) :
            comm[int(m.group(1))] = int(m.group(2))
        elif (m := _RE_FINISHED.search(line)) :
            exposed[int(m.group(1))] = int(m.group(3))

    out: list[NpuStats] = []
    for npu_id in sorted(set(wall) | set(comm) | set(exposed)):
        out.append(
            NpuStats(
                npu_id=npu_id,
                wall_cycles=wall.get(npu_id, 0),
                comm_cycles=comm.get(npu_id, 0),
                exposed_comm_cycles=exposed.get(npu_id, 0),
            )
        )
    return out


def to_dataframe(stats: list[NpuStats]) -> pd.DataFrame:
    rows = [
        {
            "npu_id": s.npu_id,
            "wall_cycles": s.wall_cycles,
            "comm_cycles": s.comm_cycles,
            "compute_cycles": s.compute_cycles,
            "exposed_comm_cycles": s.exposed_comm_cycles,
            "comm_fraction": s.comm_fraction,
        }
        for s in stats
    ]
    return pd.DataFrame(rows)


def write_parquet(stats: list[NpuStats], parquet_path: Path) -> Path:
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    to_dataframe(stats).to_parquet(parquet_path, index=False)
    return parquet_path


def parse_run_logs(log_dir: Path) -> list[NpuStats]:
    """Try log.log first (the simulator's own file in --logging-folder),
    fall back to stdout.log (our captured stdout)."""
    for name in ("log.log", "stdout.log"):
        p = log_dir / name
        stats = parse_log_file(p)
        if stats:
            return stats
    return []
