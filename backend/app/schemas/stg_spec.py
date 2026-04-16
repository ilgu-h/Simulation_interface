"""Pydantic spec for STG (symbolic_tensor_graph) trace generation.

Mirrors the actual CLI of `frameworks/symbolic_tensor_graph/main.py`. Field
names match STG's argparse names so we can build the CLI directly from a
model_dump() — no per-arg translation table to keep in sync.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ModelType = Literal["llama", "dense", "gpt", "moe", "debug"]


class StgSpec(BaseModel):
    """User-facing workload generation spec.

    `output_dir` and `output_name` are filled in by the orchestrator from the
    run id, so we don't expose them here.
    """

    model_type: ModelType = "dense"

    # Parallelism (Total NPUs = dp × tp × sp × pp, plus × ep when model_type == "moe").
    dp: int = Field(1, ge=1, description="Data parallel degree.")
    tp: int = Field(1, ge=1, description="Tensor parallel degree.")
    sp: int = Field(1, ge=1, description="Sequence parallel degree.")
    pp: int = Field(1, ge=1, description="Pipeline parallel degree.")
    ep: int = Field(1, ge=1, description="Expert parallel degree (MoE only).")

    # Model shape.
    dvocal: int = Field(32000, gt=0, description="Vocabulary size.")
    dmodel: int = Field(8192, gt=0, description="Hidden dimension.")
    dff: int = Field(28672, gt=0, description="FFN dimension.")
    head: int = Field(64, gt=0, description="Attention heads.")
    kvhead: int = Field(8, gt=0, description="KV heads (GQA).")
    num_stacks: int = Field(80, gt=0, description="Number of transformer blocks.")

    # MoE.
    experts: int = Field(8, gt=0)
    kexperts: int = Field(2, gt=0)

    # Training shape.
    batch: int = Field(64, gt=0, description="Global batch size.")
    micro_batch: int = Field(-1, description="Micro batch (-1 = auto).")
    seq: int = Field(1024, gt=0, description="Sequence length.")

    # Toggles.
    weight_sharded: bool = False
    activation_recompute: bool = False
    tpsp: bool = True
    mixed_precision: bool = False

    chakra_schema_version: str = "v0.0.4"

    @model_validator(mode="after")
    def _check_model_shape(self) -> StgSpec:
        if self.dmodel % self.head != 0:
            raise ValueError(f"dmodel ({self.dmodel}) must be divisible by head ({self.head}).")
        if self.head % self.kvhead != 0:
            raise ValueError(f"head ({self.head}) must be divisible by kvhead ({self.kvhead}).")
        if self.kexperts > self.experts:
            raise ValueError(f"kexperts ({self.kexperts}) must be <= experts ({self.experts}).")
        return self

    @property
    def total_npus(self) -> int:
        """Number of .et trace files STG will produce."""
        n = self.dp * self.tp * self.sp * self.pp
        if self.model_type == "moe":
            n *= self.ep
        return n

    def to_cli_args(self, output_dir: str, output_name: str) -> list[str]:
        """Render as `--flag value` pairs for STG's argparse."""
        d = self.model_dump()
        args = ["--output_dir", output_dir, "--output_name", output_name]
        for k, v in d.items():
            args.extend([f"--{k}", str(v)])
        return args
