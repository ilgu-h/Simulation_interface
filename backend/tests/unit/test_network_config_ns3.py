"""Unit tests for the NS3NetworkConfig schema and discriminated union."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.network_config import (
    AnalyticalNetworkConfig,
    EcnProbabilityEntry,
    EcnThresholdEntry,
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


class TestNS3ConfigFields:
    """The 42 typed config.txt fields: defaults, bounds, type coercion."""

    def test_default_cc_mode_is_12(self):
        # Matches upstream shipped default; 12 is experimental but keeps
        # current behavior for existing users.
        assert NS3NetworkConfig().cc_mode == 12

    def test_cc_mode_experimental_flag(self):
        assert NS3NetworkConfig(cc_mode=12).cc_mode_is_experimental is True
        assert NS3NetworkConfig(cc_mode=11).cc_mode_is_experimental is True
        assert NS3NetworkConfig(cc_mode=3).cc_mode_is_experimental is False
        assert NS3NetworkConfig(cc_mode=1).cc_mode_is_experimental is False

    def test_cc_mode_out_of_enum_rejected(self):
        with pytest.raises(ValidationError):
            NS3NetworkConfig(cc_mode=2)  # type: ignore[arg-type]

    def test_packet_payload_size_below_minimum_rejected(self):
        with pytest.raises(ValidationError):
            NS3NetworkConfig(packet_payload_size=10)

    def test_packet_payload_size_above_jumbo_rejected(self):
        with pytest.raises(ValidationError):
            NS3NetworkConfig(packet_payload_size=20000)

    def test_buffer_size_bounds(self):
        NS3NetworkConfig(buffer_size=1)
        NS3NetworkConfig(buffer_size=1024)
        with pytest.raises(ValidationError):
            NS3NetworkConfig(buffer_size=0)
        with pytest.raises(ValidationError):
            NS3NetworkConfig(buffer_size=2048)

    def test_error_rate_bounds(self):
        NS3NetworkConfig(error_rate_per_link=0.0)
        NS3NetworkConfig(error_rate_per_link=1.0)
        with pytest.raises(ValidationError):
            NS3NetworkConfig(error_rate_per_link=-0.1)
        with pytest.raises(ValidationError):
            NS3NetworkConfig(error_rate_per_link=1.5)

    def test_rate_string_patterns(self):
        NS3NetworkConfig(rate_ai="25Gb/s")
        NS3NetworkConfig(rate_ai="500bps")
        NS3NetworkConfig(rate_ai="2.5Mb/s")
        with pytest.raises(ValidationError):
            NS3NetworkConfig(rate_ai="25GB/s")  # wrong unit capitalization
        with pytest.raises(ValidationError):
            NS3NetworkConfig(rate_ai="25 Gb/s")  # space not allowed
        with pytest.raises(ValidationError):
            NS3NetworkConfig(rate_ai="fast")

    def test_u_target_bounds(self):
        NS3NetworkConfig(u_target=0.0)
        NS3NetworkConfig(u_target=1.0)
        with pytest.raises(ValidationError):
            NS3NetworkConfig(u_target=1.5)

    def test_pint_log_base_must_be_gt_1(self):
        with pytest.raises(ValidationError):
            NS3NetworkConfig(pint_log_base=1.0)
        NS3NetworkConfig(pint_log_base=1.01)


class TestEcnMaps:
    def test_defaults_are_6_rows(self):
        n = NS3NetworkConfig()
        assert len(n.kmax_map) == 6
        assert len(n.kmin_map) == 6
        assert len(n.pmax_map) == 6

    def test_kmin_gt_kmax_rejected(self):
        with pytest.raises(ValidationError, match="kmin.threshold"):
            NS3NetworkConfig(
                kmax_map=[EcnThresholdEntry(bandwidth_bps=10**10, threshold=100)],
                kmin_map=[EcnThresholdEntry(bandwidth_bps=10**10, threshold=500)],
                pmax_map=[EcnProbabilityEntry(bandwidth_bps=10**10, probability=0.2)],
            )

    def test_length_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="must have the same length"):
            NS3NetworkConfig(
                kmax_map=[EcnThresholdEntry(bandwidth_bps=10**10, threshold=100)],
                kmin_map=[
                    EcnThresholdEntry(bandwidth_bps=10**10, threshold=50),
                    EcnThresholdEntry(bandwidth_bps=2 * 10**10, threshold=60),
                ],
            )

    def test_row_bandwidth_mismatch_rejected(self):
        with pytest.raises(ValidationError, match="bandwidth_bps"):
            NS3NetworkConfig(
                kmax_map=[EcnThresholdEntry(bandwidth_bps=10**10, threshold=100)],
                kmin_map=[EcnThresholdEntry(bandwidth_bps=2 * 10**10, threshold=50)],
                pmax_map=[EcnProbabilityEntry(bandwidth_bps=10**10, probability=0.2)],
            )

    def test_probability_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            EcnProbabilityEntry(bandwidth_bps=10**10, probability=1.5)


class TestToConfigTxtDict:
    """The to_config_txt_dict() render — drives the per-run config.txt."""

    def test_includes_all_scalar_fields(self):
        d = NS3NetworkConfig().to_config_txt_dict()
        # Spot-check the essentials that normal users tune.
        for key in (
            "CC_MODE",
            "PACKET_PAYLOAD_SIZE",
            "BUFFER_SIZE",
            "ERROR_RATE_PER_LINK",
            "ENABLE_QCN",
            "RATE_AI",
            "RATE_HAI",
            "MIN_RATE",
        ):
            assert key in d, f"missing {key}"

    def test_includes_map_and_link_down(self):
        d = NS3NetworkConfig().to_config_txt_dict()
        assert "KMAX_MAP" in d
        assert "KMIN_MAP" in d
        assert "PMAX_MAP" in d
        assert "LINK_DOWN" in d

    def test_booleans_rendered_as_1_or_0(self):
        assert NS3NetworkConfig(enable_qcn=True).to_config_txt_dict()["ENABLE_QCN"] == "1"
        assert NS3NetworkConfig(enable_qcn=False).to_config_txt_dict()["ENABLE_QCN"] == "0"

    def test_cc_mode_override_reflected(self):
        d = NS3NetworkConfig(cc_mode=1).to_config_txt_dict()
        assert d["CC_MODE"] == "1"

    def test_kmax_map_format_matches_ns3_shipped(self):
        # ns-3 format: "N bw1 v1 bw2 v2 ... bwN vN"
        d = NS3NetworkConfig().to_config_txt_dict()
        assert d["KMAX_MAP"].startswith("6 25000000000 400")

    def test_extra_overrides_appended(self):
        n = NS3NetworkConfig(
            extra_overrides={"MY_FUTURE_KEY": "42", "CC_MODE": "99"}
        )
        d = n.to_config_txt_dict()
        # extra_overrides wins over typed fields (last-write).
        assert d["CC_MODE"] == "99"
        assert d["MY_FUTURE_KEY"] == "42"

    def test_excludes_metadata_fields(self):
        d = NS3NetworkConfig().to_config_txt_dict()
        # kind/logical_dims/paths/extra_overrides aren't config.txt keys.
        for excluded in ("KIND", "LOGICAL_DIMS", "PHYSICAL_TOPOLOGY_PATH",
                         "MIX_CONFIG_PATH", "EXTRA_OVERRIDES"):
            assert excluded not in d
