"""Subprocess wrapper for the ASTRA-sim binary.

Plays the same role as stg_runner.py but for the simulator. Streams stdout
line-by-line so the orchestrator can fan it out to SSE listeners in real
time, and tracks the live Popen so cancellation can SIGTERM it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.build.backend_adapter import BackendAdapter

# ASTRA-sim treats a comm_group path containing "empty" as "no comm groups"
# (see frameworks/astra-sim/astra-sim/workload/Workload.cc initialize_comm_groups).
COMM_GROUP_EMPTY: str = "empty"


@dataclass(frozen=True)
class AstraInvocation:
    binary: Path
    workload_prefix: Path
    comm_group_config: Path | str
    system_config: Path
    network_config: Path
    memory_config: Path
    logging_folder: Path

    def cli(self) -> list[str]:
        return [
            str(self.binary),
            f"--workload-configuration={self.workload_prefix}",
            f"--comm-group-configuration={self.comm_group_config}",
            f"--system-configuration={self.system_config}",
            f"--network-configuration={self.network_config}",
            f"--remote-memory-configuration={self.memory_config}",
            f"--logging-folder={self.logging_folder}",
        ]


def resolve_comm_group_config(workload_prefix: Path) -> Path | str:
    """Return the sibling `{prefix}.json` if it exists, else the "empty" sentinel.

    STG emits a comm-group JSON alongside `.et` trace shards; ASTRA-sim needs
    it to resolve group IDs embedded in the traces.
    """
    candidate = workload_prefix.parent / f"{workload_prefix.name}.json"
    return candidate if candidate.exists() else COMM_GROUP_EMPTY


def build_invocation(
    adapter: BackendAdapter,
    *,
    workload_prefix: Path,
    config_dir: Path,
    logging_folder: Path,
    comm_group_config: Path | str | None = None,
) -> AstraInvocation:
    resolved_comm_group = (
        comm_group_config
        if comm_group_config is not None
        else resolve_comm_group_config(workload_prefix)
    )
    return AstraInvocation(
        binary=adapter.binary_path,
        workload_prefix=workload_prefix,
        comm_group_config=resolved_comm_group,
        system_config=config_dir / "system.json",
        network_config=config_dir / "network.yml",
        memory_config=config_dir / "memory.json",
        logging_folder=logging_folder,
    )


def stream_run(
    invocation: AstraInvocation,
    *,
    run_id: str,
    log_file: Path,
) -> Iterator[tuple[str, str]]:
    """Run ASTRA-sim and yield ('line', text) for each output line.

    On exit yields ('done', f'returncode={n}'). The Popen is registered
    in the live-runs map under `run_id` so `cancel_run(run_id)` can
    SIGTERM it.

    Stdout and stderr are merged; both get persisted to `log_file`.
    """
    invocation.logging_folder.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        invocation.cli(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    register_run(run_id, proc)
    try:
        with log_file.open("w") as f:
            assert proc.stdout is not None
            for line in proc.stdout:
                f.write(line)
                f.flush()
                yield ("line", line.rstrip("\n"))
        proc.wait()
        yield ("done", f"returncode={proc.returncode}")
    finally:
        unregister_run(run_id)


# ----- in-process registry of live processes for cancellation ----------------

_live: dict[str, subprocess.Popen[str]] = {}
_lock = threading.Lock()


def register_run(run_id: str, proc: subprocess.Popen[str]) -> None:
    with _lock:
        _live[run_id] = proc


def unregister_run(run_id: str) -> None:
    with _lock:
        _live.pop(run_id, None)


def cancel_run(run_id: str) -> bool:
    """SIGTERM the live subprocess for a run, if any. Returns True if a
    process was running and was signalled."""
    with _lock:
        proc = _live.get(run_id)
    if proc is None or proc.poll() is not None:
        return False
    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    return True
