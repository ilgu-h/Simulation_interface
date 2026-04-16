"""ASTRA-sim remote memory config (JSON).

Reference: {"memory-type": "NO_MEMORY_EXPANSION"}.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal["NO_MEMORY_EXPANSION"]


class MemoryConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    memory_type: MemoryType = Field("NO_MEMORY_EXPANSION", alias="memory-type")

    def to_json_dict(self) -> dict[str, object]:
        return self.model_dump(by_alias=True)
