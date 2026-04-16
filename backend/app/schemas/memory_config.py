"""ASTRA-sim remote memory config (JSON).

Supported memory types (from AnalyticalRemoteMemory.hh):
  - NO_MEMORY_EXPANSION       no remote memory
  - PER_NODE_MEMORY_EXPANSION per-node; needs num-nodes, num-npus-per-node
  - PER_NPU_MEMORY_EXPANSION  per-NPU independent access
  - MEMORY_POOL               single shared pool, global serialization

All expansion types use remote-mem-latency (ns) and remote-mem-bw (GB/s).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal[
    "NO_MEMORY_EXPANSION",
    "PER_NODE_MEMORY_EXPANSION",
    "PER_NPU_MEMORY_EXPANSION",
    "MEMORY_POOL",
]


class MemoryConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    memory_type: MemoryType = Field("NO_MEMORY_EXPANSION", alias="memory-type")
    remote_mem_latency: int = Field(0, alias="remote-mem-latency")
    remote_mem_bw: int = Field(0, alias="remote-mem-bw")
    num_nodes: int | None = Field(None, alias="num-nodes")
    num_npus_per_node: int | None = Field(None, alias="num-npus-per-node")

    def to_json_dict(self) -> dict[str, object]:
        d: dict[str, object] = {"memory-type": self.memory_type}
        if self.memory_type != "NO_MEMORY_EXPANSION":
            d["remote-mem-latency"] = self.remote_mem_latency
            d["remote-mem-bw"] = self.remote_mem_bw
        if self.memory_type == "PER_NODE_MEMORY_EXPANSION":
            d["num-nodes"] = self.num_nodes or 0
            d["num-npus-per-node"] = self.num_npus_per_node or 0
        return d
