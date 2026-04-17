"""Unit tests for the NS3NetworkConfig schema and discriminated union."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.network_config import (
    AnalyticalNetworkConfig,
    NetworkConfigUnion,
    NS3NetworkConfig,
)


class TestNS3NetworkConfig:
    def test_defaults(self):
        n = NS3NetworkConfig()
        assert n.kind == "ns3"
        assert n.logical_dims == [8]
        assert n.total_npus == 8
        # Defaults point inside the astra-sim ns-3 submodule.
        assert "ns-3" in n.physical_topology_path
        assert n.mix_config_path.endswith("config.txt")

    def test_multi_dim_total_npus(self):
        n = NS3NetworkConfig(logical_dims=[4, 2])
        assert n.total_npus == 8

    def test_empty_logical_dims_rejected(self):
        with pytest.raises(ValidationError, match="at least one entry"):
            NS3NetworkConfig(logical_dims=[])

    def test_zero_logical_dim_rejected(self):
        with pytest.raises(ValidationError, match=">= 1"):
            NS3NetworkConfig(logical_dims=[4, 0])

    def test_to_logical_topology_json_shape(self):
        n = NS3NetworkConfig(logical_dims=[4, 2])
        payload = json.loads(n.to_logical_topology_json())
        # ns-3 expects string-typed dims in its JSON.
        assert payload == {"logical-dims": ["4", "2"]}


class TestNetworkConfigUnion:
    """Discriminated union picks the right variant (and tolerates missing tag)."""

    def setup_method(self):
        self.adapter = TypeAdapter(NetworkConfigUnion)

    def test_missing_kind_defaults_to_analytical(self):
        # Existing clients don't send `kind`. Backward-compat path.
        v = self.adapter.validate_python(
            {
                "topology": ["Ring"],
                "npus_count": [4],
                "bandwidth": [50.0],
                "latency": [500.0],
            }
        )
        assert isinstance(v, AnalyticalNetworkConfig)
        assert v.total_npus == 4

    def test_explicit_analytical_kind(self):
        v = self.adapter.validate_python(
            {
                "kind": "analytical",
                "topology": ["Ring"],
                "npus_count": [8],
                "bandwidth": [50.0],
                "latency": [500.0],
            }
        )
        assert isinstance(v, AnalyticalNetworkConfig)

    def test_ns3_kind(self):
        v = self.adapter.validate_python({"kind": "ns3", "logical_dims": [4, 2]})
        assert isinstance(v, NS3NetworkConfig)
        assert v.total_npus == 8

    def test_ns3_kind_with_defaults(self):
        v = self.adapter.validate_python({"kind": "ns3"})
        assert isinstance(v, NS3NetworkConfig)
        assert v.logical_dims == [8]

    def test_unknown_kind_fails(self):
        with pytest.raises(ValidationError):
            self.adapter.validate_python({"kind": "garnet", "logical_dims": [4]})
