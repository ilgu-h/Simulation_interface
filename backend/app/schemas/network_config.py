"""ASTRA-sim network config — discriminated by `kind`.

Two variants:

  Analytical (analytical backend family):
    kind: analytical
    topology: [ Ring ]
    npus_count: [ 8 ]
    bandwidth: [ 50.0 ]    # GB/s
    latency:   [ 500.0 ]   # ns

  NS-3 (packet-level backend):
    kind: ns3
    logical_dims: [ 8 ]
    physical_topology_path: extern/network_backend/ns-3/.../topology.txt
    mix_config_path: extern/network_backend/ns-3/.../mix/config.txt

A 2D analytical mesh is two Ring dims: topology=[Ring,Ring], npus_count=[4,4];
total NPU count is the product across dims. For ns-3 the same product rule
applies to logical_dims.

`NetworkConfig` is exported as an alias for `AnalyticalNetworkConfig` for
backward compatibility — tests and callers that reference `NetworkConfig()`
keep working. The discriminated union is `NetworkConfigUnion`, used by
`ConfigBundle.network` in `app.api.system`.
"""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag, model_validator

TopologyKind = Literal["Ring", "FullyConnected", "Switch"]


class AnalyticalNetworkConfig(BaseModel):
    kind: Literal["analytical"] = "analytical"
    topology: list[TopologyKind] = Field(default_factory=lambda: ["Ring"])
    npus_count: list[int] = Field(default_factory=lambda: [8])
    bandwidth: list[float] = Field(default_factory=lambda: [50.0])  # GB/s per dim
    latency: list[float] = Field(default_factory=lambda: [500.0])  # ns per dim

    @model_validator(mode="after")
    def _check_dims(self) -> AnalyticalNetworkConfig:
        n = len(self.topology)
        for name, lst in (
            ("npus_count", self.npus_count),
            ("bandwidth", self.bandwidth),
            ("latency", self.latency),
        ):
            if len(lst) != n:
                raise ValueError(
                    f"{name} has {len(lst)} entries; must match topology dims ({n})."
                )
        for c in self.npus_count:
            if c < 1:
                raise ValueError(f"npus_count entries must be >= 1 (got {c}).")
        for b in self.bandwidth:
            if b <= 0:
                raise ValueError(f"bandwidth entries must be > 0 (got {b}).")
        for ll in self.latency:
            if ll < 0:
                raise ValueError(f"latency entries must be >= 0 (got {ll}).")
        return self

    @property
    def total_npus(self) -> int:
        return math.prod(self.npus_count)

    def to_yaml(self) -> str:
        """Emit YAML matching the reference flow style (one line per key).

        Whitespace differences vs. the reference are intentional but kept
        minimal; comments mirror the reference (`# GB/s`, `# ns`).
        """

        def _list(values: list[object]) -> str:
            inner = ", ".join(_fmt(v) for v in values)
            return f"[ {inner} ]"

        def _fmt(v: object) -> str:
            if isinstance(v, float):
                return repr(v) if v != int(v) else f"{v:.1f}"
            return str(v)

        lines = [
            f"topology: {_list(self.topology)}",
            f"npus_count: {_list(self.npus_count)}",
            f"bandwidth: {_list(self.bandwidth)}  # GB/s",
            f"latency: {_list(self.latency)}  # ns",
            "",
        ]
        return "\n".join(lines)


class NS3NetworkConfig(BaseModel):
    """NS-3 logical topology + pointer to ns-3 physical topology & mix config.

    The physical topology and mix/config.txt live inside the ns-3 submodule
    (licensing constraints); users editing them do so in-place. We pass the
    paths through to the ns-3 binary via --network-configuration and
    --logical-topology-configuration.
    """

    kind: Literal["ns3"] = "ns3"
    logical_dims: list[int] = Field(default_factory=lambda: [8])
    physical_topology_path: str = (
        "extern/network_backend/ns-3/scratch/topology/8_nodes_1_switch_topology.txt"
    )
    mix_config_path: str = "extern/network_backend/ns-3/scratch/config/config.txt"

    @model_validator(mode="after")
    def _check_dims(self) -> NS3NetworkConfig:
        if not self.logical_dims:
            raise ValueError("logical_dims must have at least one entry.")
        for d in self.logical_dims:
            if d < 1:
                raise ValueError(f"logical_dims entries must be >= 1 (got {d}).")
        return self

    @property
    def total_npus(self) -> int:
        return math.prod(self.logical_dims)

    def to_logical_topology_json(self) -> str:
        """Serialize to ns-3's logical topology JSON format.

        ns-3 expects strings for each dim; stringify int entries.
        """
        payload = {"logical-dims": [str(d) for d in self.logical_dims]}
        return json.dumps(payload, indent=2) + "\n"


# Backward-compat alias. Existing code & tests do `NetworkConfig(...)` and
# `NetworkConfig = NetworkConfig()`; keep that working by pointing at the
# analytical variant. The ConfigBundle uses `NetworkConfigUnion` for the
# discriminated field type.
NetworkConfig = AnalyticalNetworkConfig


def _network_kind(v: Any) -> str:
    """Callable discriminator: defaults missing `kind` to analytical.

    Legacy clients (and existing integration tests) send a bare
    `{"topology": [...], "npus_count": [...]}` without a `kind` field. Fall
    back to analytical so we stay compatible without forcing a schema churn.
    """
    if isinstance(v, dict):
        return v.get("kind", "analytical")
    return getattr(v, "kind", "analytical")


NetworkConfigUnion = Annotated[
    (
        Annotated[AnalyticalNetworkConfig, Tag("analytical")]
        | Annotated[NS3NetworkConfig, Tag("ns3")]
    ),
    Discriminator(_network_kind),
]
