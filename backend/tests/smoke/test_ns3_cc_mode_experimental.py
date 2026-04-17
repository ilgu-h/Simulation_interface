"""Regression: CC_MODE 11 and 12 (HPCC-PINT variants) must not error.

These modes appear in the shipped ns-3 base config.txt and in upstream
docs, but `rdma-hw.cc` has no dedicated code path for them — ns-3's
parser silently falls through to a default. The UI shows an amber
warning to set user expectations, but nothing verifies that "silent
fall-through" stays silent.

This test locks in that contract: a run with CC_MODE 11 or 12 must
complete without ns-3 raising a parse/assert error. If a future ns-3
bump makes unknown CC_MODE fatal, these tests fail loudly instead of
runs breaking in production.

Skipped unless the ns-3 binary is built locally (same guard as
test_ns3_reference_run).
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


_MAX_WAIT_SECONDS = 180
_POLL_INTERVAL = 0.5
_WORKLOAD = (
    "frameworks/astra-sim/examples/workload/microbenchmarks/"
    "all_reduce/8npus_1MB/all_reduce"
)


async def _run_until_done(client: Any, cc_mode: int) -> tuple[str, dict[str, Any]]:
    """Run a minimal ns-3 bundle with the given CC_MODE. Returns (run_id, summary)."""
    resp = await client.post(
        "/runs",
        json={
            "workload": {"kind": "existing", "value": _WORKLOAD},
            "bundle": {
                "backend": "ns3",
                "system": {},
                "network": {"kind": "ns3", "logical_dims": [8], "cc_mode": cc_mode},
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
            print(f"[ns3-cc{cc_mode}] run={run_id} status={status}")
            last_status = status
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(_POLL_INTERVAL)
    else:
        pytest.fail(f"CC_MODE={cc_mode} run did not finish within {_MAX_WAIT_SECONDS}s")

    if last_status != "succeeded":
        events = logs_dir(run_id) / "events.log"
        if events.exists():
            print(f"\n[ns3-cc{cc_mode}] events tail for {run_id}:")
            for line in events.read_text().splitlines()[-60:]:
                print(f"  {line}")
        pytest.fail(
            f"CC_MODE={cc_mode} run status={last_status} — experimental fall-through broke"
        )

    summary = (await client.get(f"/runs/{run_id}")).json()
    return run_id, summary


@pytest.mark.parametrize("cc_mode", [11, 12])
async def test_experimental_cc_mode_falls_through_without_error(client, cc_mode):
    """ns-3 must accept CC_MODE 11/12 and run to completion.

    If ns-3's CC_MODE parser ever becomes strict, this fails and we
    either update the schema to reject these values or add a real code
    path upstream.
    """
    run_id, _ = await _run_until_done(client, cc_mode)

    # Confirm the per-run config.txt actually carried the override — proves
    # we're not silently falling back to some other default at the
    # materialize step.
    config_txt = (configs_dir(run_id) / "config.txt").read_text()
    assert f"CC_MODE {cc_mode}" in config_txt

    # events.log should be free of "ERROR" markers from ns-3 — if
    # fall-through ever becomes fatal, ns-3 prints to stderr and we'd see
    # it here.
    events = logs_dir(run_id) / "events.log"
    if events.exists():
        log_text = events.read_text().lower()
        assert "error" not in log_text, (
            f"CC_MODE={cc_mode} produced error lines in events.log — "
            "experimental fall-through may have become fatal"
        )
