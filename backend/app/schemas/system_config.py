"""ASTRA-sim system config (JSON).

Reference (frameworks/astra-sim/examples/system/native_collectives/Ring_4chunks.json):
    scheduling-policy: LIFO|FIFO
    endpoint-delay: int (ns)
    active-chunks-per-dimension: int
    preferred-dataset-splits: int
    all-{reduce,gather,scatter,to-all}-implementation: list[str]
    collective-optimization: "localBWAware" | ""
    local-mem-bw: int (GB/s)
    boost-mode: 0|1
    roofline-enabled: 0|1 (optional)
    peak-perf: int (optional)

We expose hyphenated keys via Pydantic aliases so the JSON serializer
round-trips against ASTRA-sim's expectations.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SchedulingPolicy = Literal["LIFO", "FIFO"]
CollectiveOptimization = Literal["localBWAware", ""]


class SystemConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scheduling_policy: SchedulingPolicy = Field("LIFO", alias="scheduling-policy")
    endpoint_delay: int = Field(10, alias="endpoint-delay", ge=0)
    active_chunks_per_dimension: int = Field(1, alias="active-chunks-per-dimension", ge=1)
    preferred_dataset_splits: int = Field(4, alias="preferred-dataset-splits", ge=1)

    all_reduce_implementation: list[str] = Field(
        default_factory=lambda: ["ring"], alias="all-reduce-implementation"
    )
    all_gather_implementation: list[str] = Field(
        default_factory=lambda: ["ring"], alias="all-gather-implementation"
    )
    reduce_scatter_implementation: list[str] = Field(
        default_factory=lambda: ["ring"], alias="reduce-scatter-implementation"
    )
    all_to_all_implementation: list[str] = Field(
        default_factory=lambda: ["ring"], alias="all-to-all-implementation"
    )

    collective_optimization: CollectiveOptimization = Field(
        "localBWAware", alias="collective-optimization"
    )
    local_mem_bw: int = Field(1600, alias="local-mem-bw", gt=0)
    boost_mode: int = Field(0, alias="boost-mode", ge=0, le=1)

    # Optional fields (omit from JSON when None to match reference omissions).
    roofline_enabled: int | None = Field(None, alias="roofline-enabled", ge=0, le=1)
    peak_perf: int | None = Field(None, alias="peak-perf", gt=0)

    def to_json_dict(self) -> dict[str, object]:
        # exclude_none keeps optional fields out unless explicitly set, matching
        # how the reference HGX-H100-validated.json omits roofline-enabled.
        return self.model_dump(by_alias=True, exclude_none=True)
