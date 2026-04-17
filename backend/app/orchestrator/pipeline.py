"""End-to-end run orchestration.

State machine: queued → building → running → succeeded | failed | cancelled.

Each phase appends to runs/<id>/logs/events.log (one JSON object per line)
so the SSE consumer can tail the file from any offset and replay the run.
The sentinel last line is `{"kind":"done", ...}`.

We deliberately do NOT bake threading into the consumer: the SSE endpoint
follows the events file (poll + tail), so multiple browser tabs can attach
to the same run independently and a refresh resumes from the start.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from sqlmodel import Session

from app.api.system import ConfigBundle
from app.build.backend_adapter import BackendAdapter, get_backend, is_built
from app.orchestrator.astra_runner import build_invocation, stream_run
from app.schemas.network_config import AnalyticalNetworkConfig, NS3NetworkConfig
from app.schemas.ns3_config_parser import (
    apply_overrides_dict,
    parse_config_txt,
    write_config_txt,
)
from app.storage.fs_layout import configs_dir, logs_dir, run_dir
from app.storage.registry import Artifact, Run, get_engine

REPO_ROOT = Path(__file__).resolve().parents[3]

# ----- run classification ---------------------------------------------------

# Emitted by ASTRA-sim's statistics logger once per NPU after stats are
# flushed; presence for every rank means results are on disk.
_STATS_COMPLETE_RE = re.compile(
    r"sys\[(\d+)\]\..*statistics processing end", re.IGNORECASE
)

# Per-NPU workload-finished marker: useful for progress reporting during
# long ns-3 runs where the simulator goes silent between start and finish.
_FINISHED_RE = re.compile(r"sys\[(\d+)\] finished,")

# How long (seconds) to wait between heartbeat progress events when the
# simulator produces no output. ns-3 runs can be minutes of silence
# between start and the first stats flush — without this, the SSE stream
# looks indistinguishable from a hung binary.
_HEARTBEAT_INTERVAL_S = 30.0

# glibc heap-integrity aborts and related teardown crashes. These surface
# on stderr (merged into stdout by stream_run) when the binary's destructor
# chain hits corrupted memory. They are upstream bugs, not user-caused.
_TEARDOWN_CRASH_PATTERNS = (
    # glibc malloc diagnostics — specific enough that they cannot appear
    # as legitimate simulation output.
    "malloc_consolidate",
    "double free",
    "free(): invalid pointer",
    "free(): invalid next size",
    "free(): corrupted unsorted chunks",
    "free(): corrupted size",
    "malloc(): corrupted top size",
    "realloc(): invalid pointer",
    "corrupted size vs. prev_size",
    "munmap_chunk(): invalid pointer",
    # GCC/glibc stack-guard and stdlib abort banners.
    "*** stack smashing detected",
    # Note: plain "Segmentation fault" is intentionally not listed because
    # it can appear in normal sim diagnostic output. Use SIGSEGV exit code
    # instead if we need to detect that path.
)

# Signal-as-returncode in subprocess.Popen: -N means killed by signal N.
_SIGABRT_RC = -6
_SIGTERM_RC = -15


@dataclass(frozen=True)
class RunOutcome:
    status: Literal["succeeded", "failed", "cancelled"]
    ok: bool
    warning: str | None = None


def classify_run(
    *,
    returncode: int | None,
    stats_complete_ranks: int,
    total_npus: int,
    crash_pattern_seen: bool,
) -> RunOutcome:
    """Decide the final run status from returncode + observed log signals.

    A SIGABRT after every NPU's stats were flushed is the known ASTRA-sim
    teardown bug: results are valid, so we call it 'succeeded' but attach
    a warning. A real user cancel (SIGTERM) stays 'cancelled'.
    """
    if returncode == 0:
        return RunOutcome(status="succeeded", ok=True)

    if returncode == _SIGTERM_RC:
        return RunOutcome(status="cancelled", ok=False)

    stats_complete = total_npus > 0 and stats_complete_ranks >= total_npus
    if returncode == _SIGABRT_RC and stats_complete and crash_pattern_seen:
        return RunOutcome(
            status="succeeded",
            ok=True,
            warning=(
                "ASTRA-sim aborted during teardown (heap corruption in the "
                "binary) after all NPU statistics were written. Results are "
                "valid; this is a known upstream bug."
            ),
        )

    return RunOutcome(status="failed", ok=False)


# ----- event log helpers ----------------------------------------------------


def events_log(run_id: str) -> Path:
    return logs_dir(run_id) / "events.log"


def stdout_log(run_id: str) -> Path:
    return logs_dir(run_id) / "stdout.log"


def append_event(run_id: str, kind: str, **fields: Any) -> None:
    """Append a JSON-encoded event to the run's events log.

    Kinds:
      status   {status}
      log      {text}
      done     {ok, returncode}
    """
    path = events_log(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(UTC).isoformat(), "kind": kind, **fields}
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


# ----- DB helpers -----------------------------------------------------------


def _set_status(run_id: str, status: str) -> None:
    with Session(get_engine()) as session:
        row = session.get(Run, run_id)
        if row is None:
            row = Run(id=run_id, status=status)
            session.add(row)
        else:
            row.status = status
        session.commit()
    append_event(run_id, "status", status=status)


# ----- build step -----------------------------------------------------------


def _ensure_built(adapter: BackendAdapter, run_id: str) -> bool:
    """Build the backend if its binary is missing. Returns True on success."""
    if is_built(adapter):
        return True
    append_event(run_id, "log", text=f"[build] binary missing: {adapter.binary_path}")
    append_event(run_id, "log", text=f"[build] running: {' '.join(adapter.build_cmd)}")
    proc = subprocess.run(
        adapter.build_cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    for line in proc.stdout.splitlines()[-50:]:
        append_event(run_id, "log", text=f"[build] {line}")
    if proc.returncode != 0:
        for line in proc.stderr.splitlines()[-50:]:
            append_event(run_id, "log", text=f"[build:err] {line}")
        return False
    return is_built(adapter)


# ----- materialize step -----------------------------------------------------


def _materialize(bundle: ConfigBundle, run_id: str) -> Path:
    cdir = configs_dir(run_id)
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "system.json").write_text(json.dumps(bundle.system.to_json_dict(), indent=4) + "\n")
    (cdir / "memory.json").write_text(json.dumps(bundle.memory.to_json_dict(), indent=4) + "\n")
    if isinstance(bundle.network, AnalyticalNetworkConfig):
        (cdir / "network.yml").write_text(bundle.network.to_yaml())
    elif isinstance(bundle.network, NS3NetworkConfig):
        # ns-3 needs a logical topology JSON (we materialize) plus a
        # per-run config.txt built by overlaying the user's typed fields
        # on the shipped ns-3 base config (preserves unknown upstream
        # keys like FLOW_FILE, TRACE_FILE). The physical topology file
        # itself stays inside the ns-3 submodule and is referenced by
        # path.
        (cdir / "logical_topology.json").write_text(
            bundle.network.to_logical_topology_json()
        )
        _materialize_ns3_config(bundle.network, cdir, run_id)
    return cdir


def _materialize_ns3_config(network: NS3NetworkConfig, cdir: Path, run_id: str) -> None:
    """Write runs/<id>/configs/config.txt = base config.txt + typed overrides.

    Base comes from the ns-3 submodule at the user-supplied mix_config_path.
    If the base file is missing (pre-bootstrap or user-typo path) we fall
    back to emitting just the typed fields — the resulting config.txt
    will be sparse but the simulator will still run with those values
    for the keys we set.

    The schema's ``physical_topology_path`` is project-relative (e.g.
    ``extern/network_backend/ns-3/scratch/topology/...``). ns-3 opens it
    relative to the run cwd (``ns-3/build/scratch``). We rewrite the
    TOPOLOGY_FILE key accordingly so the user sees a clean project-tree
    path in the UI but the simulator gets what it actually needs.

    Output files (FCT_OUTPUT_FILE, PFC_OUTPUT_FILE, QLEN_MON_FILE,
    TRACE_OUTPUT_FILE) are redirected to absolute paths under
    ``runs/<id>/logs/`` so per-run packet-level data stays isolated and
    our ns-3 parsers can find it. Without this redirect every run would
    clobber the shared ``scratch/output/`` directory.
    """
    import os
    from collections import OrderedDict

    astra_sim_root = REPO_ROOT / "frameworks" / "astra-sim"
    base_path = astra_sim_root / network.mix_config_path
    base: OrderedDict[str, str] = (
        parse_config_txt(base_path.read_text())
        if base_path.is_file()
        else OrderedDict()
    )
    merged = apply_overrides_dict(base, network.to_config_txt_dict())

    # Rewrite TOPOLOGY_FILE to a path relative to the ns-3 cwd.
    ns3_build_scratch = (
        astra_sim_root / "extern" / "network_backend" / "ns-3" / "build" / "scratch"
    )
    topology_abs = astra_sim_root / network.physical_topology_path
    merged["TOPOLOGY_FILE"] = os.path.relpath(topology_abs, ns3_build_scratch)

    # Redirect output files to this run's logs/ so the parsers can find
    # them and concurrent runs don't race. Absolute paths — ns-3 opens
    # these via fopen() which handles them fine regardless of cwd.
    run_logs = logs_dir(run_id)
    run_logs.mkdir(parents=True, exist_ok=True)
    merged["FCT_OUTPUT_FILE"] = str(run_logs / "fct.txt")
    merged["PFC_OUTPUT_FILE"] = str(run_logs / "pfc.txt")
    merged["QLEN_MON_FILE"] = str(run_logs / "qlen.txt")
    merged["TRACE_OUTPUT_FILE"] = str(run_logs / "mix.tr")

    (cdir / "config.txt").write_text(write_config_txt(merged))


# ----- main pipeline --------------------------------------------------------


def execute_pipeline(run_id: str, bundle: ConfigBundle, workload_prefix: Path) -> None:
    """Run materialize → build → simulate. Writes status + log events
    to runs/<id>/logs/events.log. Designed to run in a background thread
    spawned by the /runs POST handler."""
    run_root = run_dir(run_id)
    run_root.mkdir(parents=True, exist_ok=True)
    # Persist the spec for reproducibility (Phase 6 RunSpec export).
    (run_root / "spec.json").write_text(
        json.dumps(
            {
                "bundle": bundle.model_dump(by_alias=True),
                "workload_prefix": str(workload_prefix),
            },
            indent=2,
        )
    )

    try:
        adapter = get_backend(bundle.backend)
    except KeyError as e:
        _set_status(run_id, "failed")
        append_event(run_id, "log", text=f"[error] {e}")
        append_event(run_id, "done", ok=False, returncode=None)
        return

    _set_status(run_id, "building")
    if not _ensure_built(adapter, run_id):
        _set_status(run_id, "failed")
        append_event(run_id, "done", ok=False, returncode=None)
        return

    cdir = _materialize(bundle, run_id)
    _set_status(run_id, "running")

    # ns-3 runs need extra wiring: --network-configuration points at the
    # per-run config.txt we materialized in _materialize_ns3_config (which
    # overlays user overrides onto the shipped ns-3 base config), and a
    # separate --logical-topology-configuration flag carries the per-run
    # logical dims. The binary must also run with cwd=ns-3/build/scratch
    # because the config.txt references topology files via relative paths
    # like "../../scratch/topology/...".
    network_config_override: Path | None = None
    logical_topology_config: Path | None = None
    cwd: Path | None = None
    if isinstance(bundle.network, NS3NetworkConfig):
        astra_sim_root = REPO_ROOT / "frameworks" / "astra-sim"
        network_config_override = cdir / "config.txt"
        logical_topology_config = cdir / "logical_topology.json"
        ns3_scratch_build = (
            astra_sim_root / "extern" / "network_backend" / "ns-3" / "build" / "scratch"
        )
        cwd = ns3_scratch_build

    invocation = build_invocation(
        adapter,
        workload_prefix=workload_prefix,
        config_dir=cdir,
        logging_folder=logs_dir(run_id),
        network_config=network_config_override,
        logical_topology_config=logical_topology_config,
        cwd=cwd,
    )
    append_event(
        run_id,
        "log",
        text=f"[run] comm-group-configuration={invocation.comm_group_config}",
    )
    append_event(run_id, "log", text=f"[run] {' '.join(invocation.cli())}")

    last_returncode: int | None = None
    stats_complete_ranks: set[int] = set()
    crash_pattern_seen = False
    total_npus = bundle.network.total_npus
    # Shared progress state mutated from the stream loop and read from the
    # heartbeat thread. CPython's GIL makes simple int reads/writes atomic
    # but multi-step set ops are not — so we guard with an explicit lock.
    progress_lock = threading.Lock()
    progress_state = {
        "finished_count": 0,
        "last_line_ts": time.monotonic(),
    }
    # Heartbeat thread: emits periodic progress events during simulator
    # silence so the SSE stream doesn't look hung on long ns-3 runs. It's
    # a best-effort signal; the main loop's line-level events are still
    # authoritative. Daemon so the main thread's exit path takes it down.
    stop_heartbeat = threading.Event()

    def _heartbeat() -> None:
        while not stop_heartbeat.wait(_HEARTBEAT_INTERVAL_S):
            with progress_lock:
                silence = time.monotonic() - progress_state["last_line_ts"]
                finished_count = progress_state["finished_count"]
            if silence >= _HEARTBEAT_INTERVAL_S:
                append_event(
                    run_id,
                    "progress",
                    text=f"simulator running ({int(silence)}s since last output)",
                    finished=finished_count,
                    total=total_npus,
                )

    hb = threading.Thread(target=_heartbeat, daemon=True, name=f"hb-{run_id}")
    hb.start()

    finished_ranks: set[int] = set()
    try:
        for kind, payload in stream_run(invocation, run_id=run_id, log_file=stdout_log(run_id)):
            if kind == "line":
                with progress_lock:
                    progress_state["last_line_ts"] = time.monotonic()
                append_event(run_id, "log", text=payload)
                m = _STATS_COMPLETE_RE.search(payload)
                if m:
                    stats_complete_ranks.add(int(m.group(1)))
                fm = _FINISHED_RE.search(payload)
                if fm:
                    finished_ranks.add(int(fm.group(1)))
                    with progress_lock:
                        progress_state["finished_count"] = len(finished_ranks)
                    append_event(
                        run_id,
                        "progress",
                        text=f"npu {fm.group(1)} finished",
                        finished=len(finished_ranks),
                        total=total_npus,
                    )
                if not crash_pattern_seen and any(
                    p in payload for p in _TEARDOWN_CRASH_PATTERNS
                ):
                    crash_pattern_seen = True
            elif kind == "done":
                last_returncode = int(payload.split("=", 1)[1])
    except Exception as e:  # noqa: BLE001 — surface every failure mode to the user
        stop_heartbeat.set()
        _set_status(run_id, "failed")
        append_event(run_id, "log", text=f"[error] {e}")
        append_event(run_id, "done", ok=False, returncode=last_returncode)
        return
    finally:
        stop_heartbeat.set()

    outcome = classify_run(
        returncode=last_returncode,
        stats_complete_ranks=len(stats_complete_ranks),
        total_npus=total_npus,
        crash_pattern_seen=crash_pattern_seen,
    )
    if outcome.warning:
        append_event(run_id, "log", text=f"[warning] {outcome.warning}")
    _set_status(run_id, outcome.status)
    ok = outcome.ok

    # Index produced log artifacts in SQLite for results browsing later.
    with Session(get_engine()) as session:
        for log_path in sorted(logs_dir(run_id).glob("*.csv")):
            session.add(Artifact(run_id=run_id, kind="log", path=str(log_path)))
        session.add(Artifact(run_id=run_id, kind="log", path=str(stdout_log(run_id))))
        session.commit()

    append_event(run_id, "done", ok=ok, returncode=last_returncode)


def execute_pipeline_async(
    run_id: str, bundle: ConfigBundle, workload_prefix: Path
) -> threading.Thread:
    """Spawn `execute_pipeline` in a background thread."""
    t = threading.Thread(
        target=execute_pipeline,
        args=(run_id, bundle, workload_prefix),
        daemon=True,
        name=f"pipeline-{run_id}",
    )
    t.start()
    return t


# ----- helpers used by the SSE endpoint to safely re-derive paths ----------


def assert_repo_path(p: Path) -> Path:
    """Reject path-traversal attacks: workload_prefix has to live under the
    repo root or be an absolute path that does."""
    rp = p if p.is_absolute() else (REPO_ROOT / p)
    rp = rp.resolve()
    if not str(rp).startswith(str(REPO_ROOT.resolve())):
        raise ValueError(f"Path {p} escapes repo root.")
    return rp


__all__ = [
    "append_event",
    "assert_repo_path",
    "events_log",
    "execute_pipeline",
    "execute_pipeline_async",
    "stdout_log",
]
