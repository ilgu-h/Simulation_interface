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
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session

from app.api.system import ConfigBundle
from app.build.backend_adapter import BackendAdapter, get_backend, is_built
from app.orchestrator.astra_runner import build_invocation, stream_run
from app.storage.fs_layout import configs_dir, logs_dir, run_dir
from app.storage.registry import Artifact, Run, get_engine

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    (cdir / "network.yml").write_text(bundle.network.to_yaml())
    (cdir / "memory.json").write_text(json.dumps(bundle.memory.to_json_dict(), indent=4) + "\n")
    return cdir


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

    invocation = build_invocation(
        adapter,
        workload_prefix=workload_prefix,
        config_dir=cdir,
        logging_folder=logs_dir(run_id),
    )
    append_event(run_id, "log", text=f"[run] {' '.join(invocation.cli())}")

    last_returncode: int | None = None
    try:
        for kind, payload in stream_run(invocation, run_id=run_id, log_file=stdout_log(run_id)):
            if kind == "line":
                append_event(run_id, "log", text=payload)
            elif kind == "done":
                last_returncode = int(payload.split("=", 1)[1])
    except Exception as e:  # noqa: BLE001 — surface every failure mode to the user
        _set_status(run_id, "failed")
        append_event(run_id, "log", text=f"[error] {e}")
        append_event(run_id, "done", ok=False, returncode=last_returncode)
        return

    if last_returncode == 0:
        _set_status(run_id, "succeeded")
        ok = True
    else:
        # Negative returncode == killed by signal (e.g. SIGTERM from cancel).
        if last_returncode is not None and last_returncode < 0:
            _set_status(run_id, "cancelled")
        else:
            _set_status(run_id, "failed")
        ok = False

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
