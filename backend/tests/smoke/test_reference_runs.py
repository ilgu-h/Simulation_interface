"""Smoke tests reproducing the reference run_scripts through the API.

These tests actually execute ASTRA-sim and verify cycle-level agreement
with the by-hand reference outputs. They're slow (~5s each) and require
the binary to be built.
"""

from __future__ import annotations

import time

import pytest

from app.build.backend_adapter import get_backend, is_built

pytestmark = pytest.mark.skipif(
    not is_built(get_backend("analytical_cu")),
    reason="ASTRA-sim analytical binary not built",
)


async def test_reduce_scatter_4npu(client):
    """Reproduce examples/run_scripts/analytical/congestion_unaware/Ring_reducescatter_4npus.sh.

    Expected: Wall time 22240 cycles on all 4 NPUs.
    """
    resp = await client.post(
        "/runs",
        json={
            "workload": {
                "kind": "existing",
                "value": "frameworks/astra-sim/examples/workload/microbenchmarks/reduce_scatter/4npus_1MB/reduce_scatter",
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
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    # Poll for completion.
    for _ in range(30):
        status_resp = await client.get(f"/runs/{run_id}")
        status = status_resp.json()["status"]
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.5)

    assert status == "succeeded"

    summary_resp = await client.get(f"/results/{run_id}/summary")
    assert summary_resp.status_code == 200
    d = summary_resp.json()
    assert d["npu_count"] == 4
    assert d["end_to_end_cycles"] == 22240

    stats_resp = await client.get(f"/results/{run_id}/stats?view=per_npu")
    rows = stats_resp.json()
    assert len(rows) == 4
    assert all(r["wall_cycles"] == 22240 for r in rows)


async def test_all_reduce_4npu(client):
    """4-NPU all_reduce microbenchmark. Expected: 43000 cycles."""
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
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    for _ in range(30):
        status = (await client.get(f"/runs/{run_id}")).json()["status"]
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(0.5)

    assert status == "succeeded"

    d = (await client.get(f"/results/{run_id}/summary")).json()
    assert d["end_to_end_cycles"] == 43000


async def test_comparison_bandwidth_delta(client):
    """Two all_reduce runs with different bandwidths should show a cycle delta."""
    resp_a = await client.post(
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
    resp_b = await client.post(
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
                    "bandwidth": [100.0],
                    "latency": [500.0],
                },
                "memory": {},
            },
        },
    )
    id_a = resp_a.json()["run_id"]
    id_b = resp_b.json()["run_id"]

    for _ in range(30):
        sa = (await client.get(f"/runs/{id_a}")).json()["status"]
        sb = (await client.get(f"/runs/{id_b}")).json()["status"]
        if sa in ("succeeded", "failed") and sb in ("succeeded", "failed"):
            break
        time.sleep(0.5)

    cmp = (await client.get(f"/results/{id_a}/compare?with={id_b}")).json()
    assert cmp["e2e_delta_cycles"] < 0
    assert any("bandwidth" in d["path"] for d in cmp["config_diffs"])
