"""ASTRA-sim analytical-backend network config (multi-dimensional).

Reference shapes (frameworks/astra-sim/examples/network/analytical/):

  Ring_8npus.yml:
    topology: [ Ring ]
    npus_count: [ 8 ]
    bandwidth: [ 50.0 ]    # GB/s
    latency:   [ 500.0 ]   # ns

A 2D mesh is two Ring dims: topology=[Ring,Ring], npus_count=[4,4]. Total
NPU count is the product across dims.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TopologyKind = Literal["Ring", "FullyConnected", "Switch"]


class NetworkConfig(BaseModel):
    topology: list[TopologyKind] = Field(default_factory=lambda: ["Ring"])
    npus_count: list[int] = Field(default_factory=lambda: [8])
    bandwidth: list[float] = Field(default_factory=lambda: [50.0])  # GB/s per dim
    latency: list[float] = Field(default_factory=lambda: [500.0])  # ns per dim

    @model_validator(mode="after")
    def _check_dims(self) -> NetworkConfig:
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
                # Drop trailing .0 only when it would lose information? No — keep
                # one decimal so floats round-trip cleanly through YAML readers.
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
