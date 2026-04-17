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


def test_ns3_writes_per_run_config_txt():
    """Typed field overrides should land in runs/<id>/configs/config.txt."""
    bundle = ConfigBundle(
        backend="ns3",
        network=NS3NetworkConfig(
            logical_dims=[8],
            cc_mode=1,  # DCQCN override
            packet_payload_size=512,  # non-default
            enable_qcn=False,
            extra_overrides={"MY_CUSTOM_KEY": "hello"},
        ),
    )
    run_id = new_run_id()
    cdir = _materialize(bundle, run_id)

    config_txt = cdir / "config.txt"
    assert config_txt.is_file()
    content = config_txt.read_text()

    assert "CC_MODE 1" in content
    assert "PACKET_PAYLOAD_SIZE 512" in content
    assert "ENABLE_QCN 0" in content
    assert "MY_CUSTOM_KEY hello" in content

    # TOPOLOGY_FILE must be rewritten to a path relative to ns-3 cwd
    # (ns-3/build/scratch/) so ns-3 can find the file at runtime.
    topology_line = next(
        line for line in content.splitlines() if line.startswith("TOPOLOGY_FILE ")
    )
    # Should NOT contain the project-relative prefix the schema stores.
    assert "extern/network_backend/ns-3/" not in topology_line


def test_ns3_preserves_unknown_base_keys(tmp_path):
    """Keys present in the base config.txt but not in the schema pass through
    unchanged (graceful handling of upstream ns-3 drift).

    Uses an in-test base file (tmp_path) rather than the shipped ns-3 one
    so the assertion doesn't depend on the ns-3 submodule being cloned
    (which CI skips — ns-3 is opt-in, see scripts/bootstrap.sh).
    """
    fake_base = tmp_path / "base_config.txt"
    fake_base.write_text(
        "FLOW_FILE ../../scratch/output/flow.txt\n"
        "FCT_OUTPUT_FILE ../../scratch/output/fct.txt\n"
        "SOMETHING_WE_DONT_MODEL 42\n"
    )

    bundle = ConfigBundle(
        backend="ns3",
        network=NS3NetworkConfig(
            logical_dims=[8],
            # Absolute path overrides the default astra-sim-relative one
            # (pathlib: `a / abs_b == abs_b`).
            mix_config_path=str(fake_base),
        ),
    )
    run_id = new_run_id()
    cdir = _materialize(bundle, run_id)
    content = (cdir / "config.txt").read_text()

    # Keys from the fake base survive the overlay unchanged.
    assert "FLOW_FILE" in content
    assert "FCT_OUTPUT_FILE" in content
    assert "SOMETHING_WE_DONT_MODEL 42" in content
