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


class TestLogicalTopologyFlag:
    """ns-3 invocations add --logical-topology-configuration; analytical
    invocations must not."""

    def test_analytical_has_no_logical_topology_flag(self):
        inv = _sample_invocation(COMM_GROUP_EMPTY)
        assert inv.logical_topology_config is None
        assert not any(
            a.startswith("--logical-topology-configuration=") for a in inv.cli()
        )

    def test_ns3_appends_logical_topology_flag(self):
        inv = AstraInvocation(
            binary=Path("/opt/astra/AstraSim_NS3"),
            workload_prefix=Path("/tmp/run/traces/workload"),
            comm_group_config=COMM_GROUP_EMPTY,
            system_config=Path("/tmp/run/configs/system.json"),
            network_config=Path("/opt/astra/ns-3/mix/config.txt"),
            memory_config=Path("/tmp/run/configs/memory.json"),
            logging_folder=Path("/tmp/run/logs"),
            logical_topology_config=Path("/tmp/run/configs/logical_topology.json"),
            emit_logging_folder=False,
        )
        cli = inv.cli()
        assert (
            "--logical-topology-configuration=/tmp/run/configs/logical_topology.json"
            in cli
        )
        # Network config still points at ns-3's mix config (not the analytical yml).
        assert "--network-configuration=/opt/astra/ns-3/mix/config.txt" in cli
        # ns-3 doesn't accept --logging-folder; it must be suppressed.
        assert not any(a.startswith("--logging-folder=") for a in cli)


class TestResolveCommGroup:
    def test_returns_path_when_sibling_json_exists(self, tmp_path: Path):
        prefix = tmp_path / "workload"
        sibling = tmp_path / "workload.json"
        sibling.write_text(json.dumps({"1": [0, 1, 2, 3]}))
        assert resolve_comm_group_config(prefix) == sibling

    def test_returns_empty_sentinel_when_missing(self, tmp_path: Path):
        prefix = tmp_path / "workload"
        assert resolve_comm_group_config(prefix) == COMM_GROUP_EMPTY
