"""Results routes (Phase 5).

- GET /results/{run_id}/summary       end-to-end card data
- GET /results/{run_id}/stats?view=   per_npu | per_collective | per_collective_agg
- GET /results/{run_id}/timeline.json Chrome Tracing JSON (drop into Perfetto)
- GET /results/{run_id}/spec          run spec for diff in comparison view
- GET /results/{run_id}/logs/{name}   raw log file (stdout|log|err|events)
- GET /results/{run_id}/compare?with=<other>  diff summary against another run
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.parsers.astra_logs import parse_run_logs, write_parquet
from app.parsers.astra_logs import to_dataframe as npu_df
from app.parsers.et_traces import (
    aggregate_by_type,
    parse_run_traces,
)
from app.parsers.et_traces import (
    to_dataframe as coll_df,
)
from app.storage.fs_layout import logs_dir, run_dir, traces_dir

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------- helpers ---------------------------------------------------------


def _spec_path(run_id: str) -> Path:
    return run_dir(run_id) / "spec.json"


def _stats_parquet(run_id: str) -> Path:
    return run_dir(run_id) / "stats.parquet"


def _ensure_stats(run_id: str) -> list:
    """Parse logs once and cache as parquet under runs/<id>/stats.parquet."""
    parquet = _stats_parquet(run_id)
    if not parquet.exists():
        stats = parse_run_logs(logs_dir(run_id))
        if stats:
            write_parquet(stats, parquet)
        return stats
    # If parquet exists, also re-derive list from logs to keep one code path.
    return parse_run_logs(logs_dir(run_id))


def _resolve_traces_for_run(run_id: str) -> Path:
    """Heuristic: prefer runs/<id>/traces if it has .et files (own STG output);
    otherwise fall back to the workload prefix recorded in spec.json."""
    own = traces_dir(run_id)
    if own.exists() and any(own.glob("*.et")):
        return own
    spec_p = _spec_path(run_id)
    if spec_p.exists():
        try:
            spec = json.loads(spec_p.read_text())
            prefix = spec.get("workload_prefix")
            if prefix:
                return Path(prefix).parent
        except json.JSONDecodeError:
            pass
    return own


def _et_prefix_for_run(run_id: str) -> str | None:
    spec_p = _spec_path(run_id)
    if spec_p.exists():
        try:
            spec = json.loads(spec_p.read_text())
            prefix = spec.get("workload_prefix")
            if prefix:
                return Path(prefix).name
        except json.JSONDecodeError:
            pass
    return None


# ---------- summary ---------------------------------------------------------


class CollectiveAgg(BaseModel):
    comm_type: str
    count: int
    total_bytes: int


class Summary(BaseModel):
    run_id: str
    npu_count: int
    end_to_end_cycles: int
    slowest_npu: int | None
    avg_comm_fraction: float
    top_collectives: list[CollectiveAgg]


@router.get("/{run_id}/summary", response_model=Summary)
def get_summary(run_id: str) -> Summary:
    if not run_dir(run_id).exists():
        raise HTTPException(404, f"Run {run_id} not found.")

    npu_stats = _ensure_stats(run_id)
    if not npu_stats:
        return Summary(
            run_id=run_id,
            npu_count=0,
            end_to_end_cycles=0,
            slowest_npu=None,
            avg_comm_fraction=0.0,
            top_collectives=[],
        )
    walls = [s.wall_cycles for s in npu_stats]
    e2e = max(walls)
    slowest = npu_stats[walls.index(e2e)].npu_id
    avg_cf = sum(s.comm_fraction for s in npu_stats) / len(npu_stats)

    ops = parse_run_traces(_resolve_traces_for_run(run_id), prefix=_et_prefix_for_run(run_id))
    agg_df = aggregate_by_type(ops)
    top = [
        CollectiveAgg(
            comm_type=row.comm_type, count=int(row.count), total_bytes=int(row.total_bytes)
        )
        for row in agg_df.head(3).itertuples(index=False)
    ]
    return Summary(
        run_id=run_id,
        npu_count=len(npu_stats),
        end_to_end_cycles=e2e,
        slowest_npu=slowest,
        avg_comm_fraction=avg_cf,
        top_collectives=top,
    )


# ---------- stats -----------------------------------------------------------


StatsView = Literal["per_npu", "per_collective", "per_collective_agg"]


@router.get("/{run_id}/stats")
def get_stats(run_id: str, view: StatsView = "per_npu") -> JSONResponse:
    if not run_dir(run_id).exists():
        raise HTTPException(404, f"Run {run_id} not found.")
    if view == "per_npu":
        df = npu_df(_ensure_stats(run_id))
    elif view == "per_collective":
        ops = parse_run_traces(_resolve_traces_for_run(run_id), _et_prefix_for_run(run_id))
        df = coll_df(ops)
    else:
        ops = parse_run_traces(_resolve_traces_for_run(run_id), _et_prefix_for_run(run_id))
        df = aggregate_by_type(ops)
    return JSONResponse(content=json.loads(df.to_json(orient="records")))


# ---------- timeline (Chrome Tracing JSON) ---------------------------------


@router.get("/{run_id}/timeline.json")
def get_timeline(run_id: str) -> JSONResponse:
    """Synthesise a Chrome Tracing trace from per-NPU stats + collective list.

    Each NPU gets one 'wall' event spanning end-to-end and one 'comm' event
    sized to its measured comm time. Collectives from the .et show as
    instant marks at NPU lane 0. Drop the JSON into ui.perfetto.dev.

    This is approximate (we don't have per-collective issue timestamps from
    the analytical backend), but matches the cycle counts and surfaces the
    workload composition.
    """
    if not run_dir(run_id).exists():
        raise HTTPException(404, f"Run {run_id} not found.")
    npu_stats = _ensure_stats(run_id)
    ops = parse_run_traces(_resolve_traces_for_run(run_id), _et_prefix_for_run(run_id))

    # Convert cycles to microseconds assuming 1 GHz NPU clock (configurable
    # later via /backends).
    cycles_to_us = 1e-3
    events: list[dict] = []
    for s in npu_stats:
        wall_us = s.wall_cycles * cycles_to_us
        comm_us = s.comm_cycles * cycles_to_us
        compute_us = max(0.0, wall_us - comm_us)
        events.append(
            {
                "name": "compute",
                "cat": "wall",
                "ph": "X",
                "ts": 0.0,
                "dur": compute_us,
                "pid": s.npu_id,
                "tid": "compute",
            }
        )
        events.append(
            {
                "name": "comm",
                "cat": "comm",
                "ph": "X",
                "ts": compute_us,
                "dur": comm_us,
                "pid": s.npu_id,
                "tid": "comm",
                "args": {"comm_cycles": s.comm_cycles},
            }
        )

    # Collective markers — instant events on each NPU.
    for op in ops:
        events.append(
            {
                "name": op.comm_type,
                "cat": "collective",
                "ph": "i",
                "ts": 0.0,
                "pid": op.npu_id,
                "tid": "collective",
                "s": "p",  # process-scoped
                "args": {
                    "name": op.name,
                    "node_id": op.node_id,
                    "comm_size_bytes": op.comm_size_bytes,
                },
            }
        )

    return JSONResponse(
        content={
            "displayTimeUnit": "ns",
            "metadata": {"run_id": run_id, "npu_count": len(npu_stats)},
            "traceEvents": events,
        }
    )


# ---------- spec + logs -----------------------------------------------------


@router.get("/{run_id}/spec")
def get_spec(run_id: str) -> JSONResponse:
    p = _spec_path(run_id)
    if not p.exists():
        raise HTTPException(404, f"spec.json missing for run {run_id}.")
    return JSONResponse(content=json.loads(p.read_text()))


@router.get("/{run_id}/logs/{name}")
def get_log(run_id: str, name: str) -> FileResponse:
    if not name.replace(".", "").replace("_", "").isalnum():
        raise HTTPException(400, "Log name contains forbidden characters.")
    p = logs_dir(run_id) / name
    if not p.exists():
        raise HTTPException(404, f"Log {name} not found.")
    return FileResponse(p, media_type="text/plain", filename=p.name)


# ---------- comparison ------------------------------------------------------


class FieldDiff(BaseModel):
    path: str
    a: object | None
    b: object | None


class CompareResult(BaseModel):
    a: str
    b: str
    summary_a: Summary
    summary_b: Summary
    e2e_delta_cycles: int
    e2e_delta_pct: float
    config_diffs: list[FieldDiff]


def _flatten(obj, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


@router.get("/{run_id}/compare", response_model=CompareResult)
def compare_runs(run_id: str, with_: str = Query(..., alias="with")) -> CompareResult:
    a_summary = get_summary(run_id)
    b_summary = get_summary(with_)
    a_spec = json.loads(_spec_path(run_id).read_text()) if _spec_path(run_id).exists() else {}
    b_spec = json.loads(_spec_path(with_).read_text()) if _spec_path(with_).exists() else {}
    flat_a, flat_b = _flatten(a_spec), _flatten(b_spec)
    keys = sorted(set(flat_a) | set(flat_b))
    diffs = [
        FieldDiff(path=k, a=flat_a.get(k), b=flat_b.get(k))
        for k in keys
        if flat_a.get(k) != flat_b.get(k)
    ]
    e2e_delta = b_summary.end_to_end_cycles - a_summary.end_to_end_cycles
    e2e_pct = (
        (e2e_delta / a_summary.end_to_end_cycles * 100.0)
        if a_summary.end_to_end_cycles
        else 0.0
    )
    return CompareResult(
        a=run_id,
        b=with_,
        summary_a=a_summary,
        summary_b=b_summary,
        e2e_delta_cycles=e2e_delta,
        e2e_delta_pct=e2e_pct,
        config_diffs=diffs,
    )
