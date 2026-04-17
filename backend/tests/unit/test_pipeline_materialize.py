"""Unit tests for pipeline._materialize variant dispatch.

Analytical bundles write configs/network.yml; ns3 bundles write
configs/logical_topology.json instead (physical topology + mix config
references stay as paths since they live inside the ns-3 submodule).
"""

from __future__ import annotations

import json

from app.api.system import ConfigBundle
from app.orchestrator.pipeline import _materialize
from app.schemas.network_config import AnalyticalNetworkConfig, NS3NetworkConfig
from app.storage.fs_layout import new_run_id


def test_analytical_writes_network_yml():
    bundle = ConfigBundle(
        backend="analytical_cu",
        network=AnalyticalNetworkConfig(
            topology=["Ring"], npus_count=[4], bandwidth=[50.0], latency=[500.0]
        ),
    )
    run_id = new_run_id()
    cdir = _materialize(bundle, run_id)
    assert (cdir / "network.yml").is_file()
    assert not (cdir / "logical_topology.json").exists()
    assert (cdir / "system.json").is_file()
    assert (cdir / "memory.json").is_file()


def test_ns3_writes_logical_topology_json():
    bundle = ConfigBundle(
        backend="ns3",
        network=NS3NetworkConfig(logical_dims=[4, 2]),
    )
    run_id = new_run_id()
    cdir = _materialize(bundle, run_id)
    assert (cdir / "logical_topology.json").is_file()
    assert not (cdir / "network.yml").exists()

    payload = json.loads((cdir / "logical_topology.json").read_text())
    # ns-3 expects string-typed dims in its JSON.
    assert payload == {"logical-dims": ["4", "2"]}
