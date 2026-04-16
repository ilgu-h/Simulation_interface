"""Unit tests for ASTRA-sim invocation building."""

from __future__ import annotations

import json
from pathlib import Path

from app.orchestrator.astra_runner import (
    COMM_GROUP_EMPTY,
    AstraInvocation,
    resolve_comm_group_config,
)


def _sample_invocation(comm_group: Path | str) -> AstraInvocation:
    return AstraInvocation(
        binary=Path("/opt/astra/AstraSim"),
        workload_prefix=Path("/tmp/run/traces/workload"),
        comm_group_config=comm_group,
        system_config=Path("/tmp/run/configs/system.json"),
        network_config=Path("/tmp/run/configs/network.yml"),
        memory_config=Path("/tmp/run/configs/memory.json"),
        logging_folder=Path("/tmp/run/logs"),
    )


class TestCli:
    def test_includes_comm_group_path(self):
        inv = _sample_invocation(Path("/tmp/run/traces/workload.json"))
        assert (
            "--comm-group-configuration=/tmp/run/traces/workload.json" in inv.cli()
        )

    def test_accepts_empty_sentinel(self):
        inv = _sample_invocation(COMM_GROUP_EMPTY)
        assert "--comm-group-configuration=empty" in inv.cli()

    def test_flag_order_stable(self):
        inv = _sample_invocation(COMM_GROUP_EMPTY)
        cli = inv.cli()
        workload_idx = next(i for i, a in enumerate(cli) if a.startswith("--workload-"))
        comm_idx = next(i for i, a in enumerate(cli) if a.startswith("--comm-group-"))
        assert comm_idx == workload_idx + 1


class TestResolveCommGroup:
    def test_returns_path_when_sibling_json_exists(self, tmp_path: Path):
        prefix = tmp_path / "workload"
        sibling = tmp_path / "workload.json"
        sibling.write_text(json.dumps({"1": [0, 1, 2, 3]}))
        assert resolve_comm_group_config(prefix) == sibling

    def test_returns_empty_sentinel_when_missing(self, tmp_path: Path):
        prefix = tmp_path / "workload"
        assert resolve_comm_group_config(prefix) == COMM_GROUP_EMPTY
