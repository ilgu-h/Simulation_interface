"""Per-collective info extracted from the source .et traces.

ASTRA-sim's analytical-backend log doesn't break down per-collective stats,
but the original Chakra .et files do specify each planned collective with
its type and size. We aggregate those across all NPUs to give the user a
"workload composition" view.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from chakra.schema.protobuf.et_def_pb2 import (
    COMM_COLL_NODE,
    CollectiveCommType,
    GlobalMetadata,
    Node,
)
from chakra.src.third_party.utils.protolib import decodeMessage as _decode
from chakra.src.third_party.utils.protolib import openFileRd as _open_rd

_TYPE_NAMES = {v: k for k, v in CollectiveCommType.items()}


@dataclass(frozen=True)
class CollectiveOp:
    npu_id: int
    node_id: int
    name: str
    comm_type: str
    comm_size_bytes: int


def _attr_value(attr) -> object:
    # AttributeProto carries a oneof — read whichever is set.
    for f in ("uint64_val", "int64_val", "uint32_val", "int32_val", "bool_val",
              "float_val", "double_val", "string_val"):
        if attr.HasField(f) if hasattr(attr, "HasField") else getattr(attr, f, None):
            return getattr(attr, f)
    return None


def _attrs(node: Node) -> dict[str, object]:
    out: dict[str, object] = {}
    for a in node.attr:
        out[a.name] = _attr_value(a)
    return out


def parse_et(et_path: Path, npu_id: int) -> list[CollectiveOp]:
    fp = _open_rd(str(et_path))
    try:
        meta = GlobalMetadata()
        _decode(fp, meta)
        out: list[CollectiveOp] = []
        node = Node()
        while _decode(fp, node):
            if node.type == COMM_COLL_NODE:
                a = _attrs(node)
                comm_type_val = int(a.get("comm_type", -1) or 0)
                size = int(a.get("comm_size", 0) or 0)
                out.append(
                    CollectiveOp(
                        npu_id=npu_id,
                        node_id=node.id,
                        name=node.name,
                        comm_type=_TYPE_NAMES.get(comm_type_val, f"UNKNOWN({comm_type_val})"),
                        comm_size_bytes=size,
                    )
                )
            node = Node()
    finally:
        fp.close()
    return out


def parse_run_traces(traces_dir: Path, prefix: str | None = None) -> list[CollectiveOp]:
    """Parse every .et in `traces_dir` matching `<prefix>.<npu>.et`.

    If `prefix` is None, infers it from the first .et file's basename.
    """
    files = sorted(traces_dir.glob("*.et"))
    if not files:
        return []
    if prefix is None:
        # workload.7.et → workload
        first_stem = files[0].name.rsplit(".", 2)[0]
        prefix = first_stem
    out: list[CollectiveOp] = []
    for f in files:
        try:
            npu_id = int(f.name.rsplit(".", 2)[1])
        except (ValueError, IndexError):
            continue
        out.extend(parse_et(f, npu_id))
    return out


def to_dataframe(ops: list[CollectiveOp]) -> pd.DataFrame:
    rows = [
        {
            "npu_id": o.npu_id,
            "node_id": o.node_id,
            "name": o.name,
            "comm_type": o.comm_type,
            "comm_size_bytes": o.comm_size_bytes,
        }
        for o in ops
    ]
    return pd.DataFrame(rows)


def aggregate_by_type(ops: list[CollectiveOp]) -> pd.DataFrame:
    """Roll up to (comm_type, count, total_bytes) for the summary card."""
    counts: dict[str, int] = defaultdict(int)
    sizes: dict[str, int] = defaultdict(int)
    for o in ops:
        counts[o.comm_type] += 1
        sizes[o.comm_type] += o.comm_size_bytes
    rows = [
        {"comm_type": k, "count": counts[k], "total_bytes": sizes[k]} for k in sorted(counts)
    ]
    return pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)
