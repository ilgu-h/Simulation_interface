"""End-to-end smoke test for the ns3 backend.

Skipped unless the ns-3 binary has been built locally. Drives the full
orchestrator pipeline (/runs → building → running → succeeded) via the
in-process FastAPI client — no uvicorn needed.

Run manually:
    cd backend && pytest tests/smoke/test_ns3_reference_run.py -s -v
"""

from __future__ import annotations

import time

import pytest

from app.build.backend_adapter import get_backend, is_built

pytestmark = pytest.mark.skipif(
    not is_built(get_backend("ns3")),
    reason="ns3 binary not built (run `ENABLE_NS3=1 bash scripts/bootstrap.sh` first)",
)


# ns-3 simulations are slower than analytical; give them a generous timeout.
_MAX_WAIT_SECONDS = 180
_POLL_INTERVAL = 0.5


async def test_ns3_all_reduce_8npu(client):
    resp = await client.post(
        "/runs",
        json={
            "workload": {
                "kind": "existing",
                "value": (
                    "frameworks/astra-sim/examples/workload/microbenchmarks/"
                    "all_reduce/8npus_1MB/all_reduce"
                ),
            },
            "bundle": {
                "backend": "ns3",
                "system": {},
                "network": {"kind": "ns3", "logical_dims": [8]},
                "memory": {},
            },
        },
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    deadline = time.monotonic() + _MAX_WAIT_SECONDS
    last_status = None
    while time.monotonic() < deadline:
        status_resp = await client.get(f"/runs/{run_id}")
        status = status_resp.json()["status"]
        if status != last_status:
            print(f"[ns3-smoke] status={status}")
            last_status = status
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(_POLL_INTERVAL)
    else:
        pytest.fail(f"ns3 run did not finish within {_MAX_WAIT_SECONDS}s (last={last_status})")

    # On failure, dump the tail of the events log to aid debugging.
    if last_status != "succeeded":
        from app.storage.fs_layout import logs_dir

        events = logs_dir(run_id) / "events.log"
        if events.exists():
            print(f"\n[ns3-smoke] events tail for {run_id} ({events}):")
            for line in events.read_text().splitlines()[-60:]:
                print(f"  {line}")
        pytest.fail(f"ns3 run status={last_status} (expected succeeded)")

    # Summary should be available.
    summary_resp = await client.get(f"/results/{run_id}/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert summary["npu_count"] == 8, summary
