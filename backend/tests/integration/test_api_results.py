"""Integration tests for results endpoints using real run data."""

from __future__ import annotations

import time

import pytest

from app.build.backend_adapter import get_backend, is_built

pytestmark = pytest.mark.skipif(
    not is_built(get_backend("analytical_cu")),
    reason="ASTRA-sim binary not built",
)


@pytest.fixture
async def finished_run_id(client):
    """Start a 4-NPU run and wait for it to finish."""
    resp = await client.post(
        "/runs",
        json={
            "workload": {
                "kind": "existing",
                "value": "frameworks/astra-sim/examples/workload/microbenchmarks/all_reduce/4npus_1MB/all_reduce",
            },
            "bundle": {
                "backend": "analytical_cu",
                "system": {},
                "network": {
                    "topology": ["Ring"],
                    "npus_count": [4],
                    "bandwidth": [50.0],
                    "latency": [500.0],
                },
                "memory": {},
            },
        },
    )
    run_id = resp.json()["run_id"]
    for _ in range(30):
        s = (await client.get(f"/runs/{run_id}")).json()["status"]
        if s in ("succeeded", "failed"):
            break
        time.sleep(0.3)
    return run_id


async def test_summary(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/summary")
    assert resp.status_code == 200
    d = resp.json()
    assert d["npu_count"] == 4
    assert d["end_to_end_cycles"] == 43000
    assert d["slowest_npu"] == 0
    assert len(d["top_collectives"]) >= 1


async def test_stats_per_npu(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/stats?view=per_npu")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 4
    assert all(r["wall_cycles"] == 43000 for r in rows)


async def test_stats_per_collective(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/stats?view=per_collective")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 4
    assert all(r["comm_type"] == "ALL_REDUCE" for r in rows)


async def test_stats_per_collective_agg(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/stats?view=per_collective_agg")
    assert resp.status_code == 200
    rows = resp.json()
    assert rows[0]["comm_type"] == "ALL_REDUCE"
    assert rows[0]["count"] == 4


async def test_timeline_json(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/timeline.json")
    assert resp.status_code == 200
    d = resp.json()
    assert "traceEvents" in d
    assert len(d["traceEvents"]) >= 8


async def test_spec(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/spec")
    assert resp.status_code == 200
    d = resp.json()
    assert "bundle" in d


async def test_spec_yaml(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/spec.yaml")
    assert resp.status_code == 200
    assert "bundle" in resp.text


async def test_logs_stdout(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/logs/stdout.log")
    assert resp.status_code == 200
    assert "Wall time" in resp.text


async def test_logs_forbidden_chars(client, finished_run_id):
    resp = await client.get(f"/results/{finished_run_id}/logs/../../etc/passwd")
    # Path traversal via route segments is blocked by FastAPI/Starlette itself.
    assert resp.status_code in (400, 404)


async def test_summary_404(client):
    resp = await client.get("/results/nonexistent_run_abc/summary")
    assert resp.status_code == 404
