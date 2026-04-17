"""Integration tests for core API endpoints."""

from __future__ import annotations


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_backends(client):
    resp = await client.get("/backends")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    names = [b["name"] for b in data]
    assert "analytical_cu" in names


async def test_presets(client):
    resp = await client.get("/workloads/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 3
    ids = [p["id"] for p in data]
    assert "llama-7b" in ids


async def test_workload_library(client):
    resp = await client.get("/workloads/library")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_configs_validate_ok(client):
    resp = await client.post(
        "/configs/validate",
        json={
            "backend": "analytical_cu",
            "system": {},
            "network": {"topology": ["Ring"], "npus_count": [4], "bandwidth": [50.0], "latency": [500.0]},
            "memory": {},
            "expected_npus": 4,
        },
    )
    assert resp.status_code == 200
    d = resp.json()
    assert d["ok"] is True
    assert d["total_npus"] == 4


async def test_configs_validate_npu_mismatch(client):
    resp = await client.post(
        "/configs/validate",
        json={
            "backend": "analytical_cu",
            "system": {},
            "network": {"topology": ["Ring"], "npus_count": [4], "bandwidth": [50.0], "latency": [500.0]},
            "memory": {},
            "expected_npus": 8,
        },
    )
    d = resp.json()
    assert d["ok"] is False
    assert any("mismatch" in i["message"].lower() or "expects" in i["message"] for i in d["issues"])


async def test_configs_validate_ns3_variant(client):
    # Discriminator picks NS3 variant; total_npus is computed from logical_dims.
    resp = await client.post(
        "/configs/validate",
        json={
            "backend": "ns3",
            "system": {},
            "network": {"kind": "ns3", "logical_dims": [4, 2]},
            "memory": {},
            "expected_npus": 8,
        },
    )
    assert resp.status_code == 200
    d = resp.json()
    assert d["ok"] is True
    assert d["total_npus"] == 8
    # No errors expected; warnings may or may not appear depending on whether
    # the ns-3 submodule is cloned and the binary is built.
    assert all(i["severity"] != "error" for i in d["issues"])


async def test_configs_validate_ns3_npu_mismatch(client):
    resp = await client.post(
        "/configs/validate",
        json={
            "backend": "ns3",
            "system": {},
            "network": {"kind": "ns3", "logical_dims": [4, 2]},
            "memory": {},
            "expected_npus": 16,
        },
    )
    d = resp.json()
    assert d["ok"] is False
    fields = {i["field"] for i in d["issues"] if i["severity"] == "error"}
    assert "network.logical_dims" in fields


async def test_configs_materialize(client):
    resp = await client.post(
        "/configs/materialize",
        json={
            "backend": "analytical_cu",
            "system": {},
            "network": {"topology": ["Ring"], "npus_count": [4], "bandwidth": [50.0], "latency": [500.0]},
            "memory": {},
        },
    )
    assert resp.status_code == 200
    d = resp.json()
    assert "run_id" in d
    assert "network" in d["files"]


async def test_runs_validate_reference(client):
    resp = await client.post(
        "/runs/validate",
        json={
            "workload": {
                "kind": "existing",
                "value": "frameworks/astra-sim/examples/workload/microbenchmarks/reduce_scatter/4npus_1MB/reduce_scatter",
            },
            "bundle": {
                "backend": "analytical_cu",
                "system": {},
                "network": {"topology": ["Ring"], "npus_count": [4], "bandwidth": [50.0], "latency": [500.0]},
                "memory": {},
            },
        },
    )
    assert resp.status_code == 200
    d = resp.json()
    assert d["ok"] is True
    assert d["workload"]["trace_count"] == 4


async def test_runs_validate_missing_workload(client):
    resp = await client.post(
        "/runs/validate",
        json={
            "workload": {"kind": "existing", "value": "nonexistent/path/traces"},
            "bundle": {
                "backend": "analytical_cu",
                "system": {},
                "network": {"topology": ["Ring"], "npus_count": [4], "bandwidth": [50.0], "latency": [500.0]},
                "memory": {},
            },
        },
    )
    d = resp.json()
    assert d["ok"] is False


async def test_get_run_404(client):
    resp = await client.get("/runs/nonexistent_run_id")
    assert resp.status_code == 404
