"""End-to-end smoke test for the ns3 backend.

Skipped unless the ns-3 binary has been built locally. Drives the full
orchestrator pipeline (/runs → building → running → succeeded) via the
in-process FastAPI client — no uvicorn needed.

Run manually:
    cd backend && pytest tests/smoke/test_ns3_reference_run.py -s -v
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app.build.backend_adapter import get_backend, is_built
from app.storage.fs_layout import configs_dir, logs_dir

pytestmark = pytest.mark.skipif(
    not is_built(get_backend("ns3")),
    reason="ns3 binary not built (run `ENABLE_NS3=1 bash scripts/bootstrap.sh` first)",
)


# ns-3 simulations are slower than analytical; give them a generous timeout.
_MAX_WAIT_SECONDS = 180
_POLL_INTERVAL = 0.5

_WORKLOAD = (
    "frameworks/astra-sim/examples/workload/microbenchmarks/"
    "all_reduce/8npus_1MB/all_reduce"
)


async def _run_bundle(client: Any, network: dict[str, Any]) -> dict[str, Any]:
    """Submit a run, poll to completion, return the /summary payload.

    Fails the test with an events-log dump if the run doesn't succeed.
    """
    resp = await client.post(
        "/runs",
        json={
            "workload": {"kind": "existing", "value": _WORKLOAD},
            "bundle": {
                "backend": "ns3",
                "system": {},
                "network": network,
                "memory": {},
            },
        },
    )
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]

    deadline = time.monotonic() + _MAX_WAIT_SECONDS
    last_status = None
    while time.monotonic() < deadline:
        status = (await client.get(f"/runs/{run_id}")).json()["status"]
        if status != last_status:
            print(f"[ns3-smoke] run={run_id} status={status}")
            last_status = status
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(_POLL_INTERVAL)
    else:
        pytest.fail(f"ns3 run did not finish within {_MAX_WAIT_SECONDS}s")

    if last_status != "succeeded":
        events = logs_dir(run_id) / "events.log"
        if events.exists():
            print(f"\n[ns3-smoke] events tail for {run_id} ({events}):")
            for line in events.read_text().splitlines()[-60:]:
                print(f"  {line}")
        pytest.fail(f"ns3 run status={last_status} (expected succeeded)")

    summary = (await client.get(f"/results/{run_id}/summary")).json()
    summary["_run_id"] = run_id
    return summary


async def test_ns3_all_reduce_8npu_default(client):
    """Baseline: default config (CC_MODE=12) finishes and reports 8 NPUs."""
    summary = await _run_bundle(client, {"kind": "ns3", "logical_dims": [8]})
    assert summary["npu_count"] == 8
    assert summary["end_to_end_cycles"] > 0

    # Per-run config.txt must exist and contain our expected overrides.
    config_txt = (configs_dir(summary["_run_id"]) / "config.txt").read_text()
    assert "CC_MODE 12" in config_txt
    # And it must contain base-config keys we don't explicitly set (drift
    # passthrough).
    assert "FLOW_FILE" in config_txt


async def test_ns3_cc_mode_override_reaches_binary(client):
    """Proves user-supplied overrides actually change simulator behavior.

    Runs the same workload twice — once with default CC_MODE (12), once
    with CC_MODE=3 (HPCC) — and asserts end-to-end cycles differ.

    We use HPCC rather than DCQCN here because 1MB all-reduce flows on
    50Mb/s links are too short to exercise DCQCN's queue-build response;
    DCQCN and the default CC_MODE produce identical cycles for this
    workload (both ~154096). HPCC marks/paces packets differently and
    shows observable delta even on short flows.

    If the override path were broken (per-run config.txt not materialized,
    or not passed via --network-configuration), CC_MODE=3 would still
    produce the baseline cycle count.
    """
    baseline = await _run_bundle(client, {"kind": "ns3", "logical_dims": [8]})
    hpcc = await _run_bundle(
        client, {"kind": "ns3", "logical_dims": [8], "cc_mode": 3}
    )

    # Confirm the per-run config actually carried the override.
    hpcc_config = (configs_dir(hpcc["_run_id"]) / "config.txt").read_text()
    assert "CC_MODE 3" in hpcc_config

    baseline_cycles = baseline["end_to_end_cycles"]
    hpcc_cycles = hpcc["end_to_end_cycles"]
    print(
        f"[ns3-smoke] baseline cycles={baseline_cycles}, hpcc cycles={hpcc_cycles}"
    )
    assert baseline_cycles != hpcc_cycles, (
        f"CC_MODE override had no effect: both runs produced {baseline_cycles} cycles. "
        "Per-run config.txt or --network-configuration wiring is broken."
    )
