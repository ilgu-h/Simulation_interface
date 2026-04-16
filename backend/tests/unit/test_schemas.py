"""Unit tests for Pydantic config + STG schemas."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.memory_config import MemoryConfig
from app.schemas.network_config import NetworkConfig
from app.schemas.stg_spec import StgSpec
from app.schemas.system_config import SystemConfig


class TestStgSpec:
    def test_defaults(self):
        s = StgSpec()
        assert s.model_type == "dense"
        assert s.total_npus == 1

    def test_total_npus_dense(self):
        s = StgSpec(dp=2, tp=4, pp=2, sp=1)
        assert s.total_npus == 16

    def test_total_npus_moe_includes_ep(self):
        s = StgSpec(model_type="moe", dp=2, tp=2, pp=1, ep=4)
        assert s.total_npus == 2 * 2 * 4

    def test_dmodel_head_validation(self):
        with pytest.raises(ValidationError, match="divisible by head"):
            StgSpec(dmodel=100, head=7)

    def test_kvhead_validation(self):
        with pytest.raises(ValidationError, match="divisible by kvhead"):
            StgSpec(head=32, kvhead=5)

    def test_kexperts_validation(self):
        with pytest.raises(ValidationError, match="kexperts"):
            StgSpec(experts=4, kexperts=8)

    def test_to_cli_args(self):
        s = StgSpec(dp=2, tp=2, pp=1, model_type="llama")
        args = s.to_cli_args("/out", "trace")
        assert "--output_dir" in args
        assert "/out" in args
        assert "--dp" in args
        assert "2" in args
        assert "--model_type" in args
        assert "llama" in args

    def test_negative_fields_rejected(self):
        with pytest.raises(ValidationError):
            StgSpec(dp=0)


class TestNetworkConfig:
    def test_defaults(self):
        n = NetworkConfig()
        assert n.topology == ["Ring"]
        assert n.total_npus == 8

    def test_multidim_total(self):
        n = NetworkConfig(
            topology=["Ring", "Ring"],
            npus_count=[4, 4],
            bandwidth=[50.0, 50.0],
            latency=[500.0, 500.0],
        )
        assert n.total_npus == 16

    def test_dim_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="must match topology dims"):
            NetworkConfig(topology=["Ring"], npus_count=[4, 4], bandwidth=[50.0], latency=[500.0])

    def test_negative_bandwidth_rejected(self):
        with pytest.raises(ValidationError, match="bandwidth"):
            NetworkConfig(topology=["Ring"], npus_count=[4], bandwidth=[-1.0], latency=[500.0])

    def test_to_yaml_ring_8(self):
        n = NetworkConfig(topology=["Ring"], npus_count=[8], bandwidth=[50.0], latency=[500.0])
        yaml = n.to_yaml()
        assert "topology: [ Ring ]" in yaml
        assert "npus_count: [ 8 ]" in yaml
        assert "# GB/s" in yaml
        assert "# ns" in yaml

    def test_to_yaml_2d(self):
        n = NetworkConfig(
            topology=["Ring", "FullyConnected"],
            npus_count=[4, 2],
            bandwidth=[50.0, 100.0],
            latency=[500.0, 200.0],
        )
        yaml = n.to_yaml()
        assert "Ring, FullyConnected" in yaml
        assert "4, 2" in yaml


class TestSystemConfig:
    def test_defaults(self):
        s = SystemConfig()
        assert s.scheduling_policy == "LIFO"
        assert s.local_mem_bw == 1600

    def test_to_json_dict_uses_aliases(self):
        d = SystemConfig().to_json_dict()
        assert "scheduling-policy" in d
        assert "scheduling_policy" not in d

    def test_exclude_none_omits_optional(self):
        d = SystemConfig().to_json_dict()
        assert "roofline-enabled" not in d
        assert "peak-perf" not in d

    def test_include_optional_when_set(self):
        d = SystemConfig(roofline_enabled=0, peak_perf=900).to_json_dict()
        assert d["roofline-enabled"] == 0
        assert d["peak-perf"] == 900

    def test_json_roundtrip(self):
        d = SystemConfig(roofline_enabled=1, peak_perf=500).to_json_dict()
        raw = json.dumps(d)
        restored = json.loads(raw)
        assert restored["scheduling-policy"] == "LIFO"


class TestMemoryConfig:
    def test_defaults(self):
        m = MemoryConfig()
        assert m.to_json_dict() == {"memory-type": "NO_MEMORY_EXPANSION"}
