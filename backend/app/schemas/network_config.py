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
    cc_mode: 12
    packet_payload_size: 1000
    ... plus ~40 more typed ns-3 parameters

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
from collections import OrderedDict
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag, model_validator

TopologyKind = Literal["Ring", "FullyConnected", "Switch"]

# Rate values for ns-3 are strings like "50Mb/s", "1000Mb/s", "5Gb/s".
RATE_PATTERN = r"^\d+(\.\d+)?(bps|Kb/s|Mb/s|Gb/s)$"

# ns-3 congestion control modes. Only 1/3/7/8/10 are implemented in
# rdma-hw.cc. 11 and 12 appear in upstream docs + the shipped default
# config but have no code implementation — ns-3's parser silently
# ignores unknown values, so setting 11/12 falls through to some
# default path. We accept them (default is 12 to preserve upstream
# compatibility) but flag them as experimental in UI/validation.
CCMode = Literal[1, 3, 7, 8, 10, 11, 12]


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


# ---- ns-3 sub-types --------------------------------------------------------


class EcnThresholdEntry(BaseModel):
    """One row of ns-3's KMAX_MAP / KMIN_MAP: (link bandwidth in bps, threshold).

    The threshold unit is bytes (switch buffer); ns-3 reads it as uint32.
    """

    bandwidth_bps: int = Field(ge=0)
    threshold: int = Field(ge=0)


class EcnProbabilityEntry(BaseModel):
    """One row of ns-3's PMAX_MAP: (link bandwidth in bps, drop probability)."""

    bandwidth_bps: int = Field(ge=0)
    probability: float = Field(ge=0.0, le=1.0)


class LinkDown(BaseModel):
    """ns-3's LINK_DOWN tuple: simulates a link going down at `time` ns.

    All zeros disables the feature.
    """

    src: int = 0
    dst: int = 0
    time: int = 0


def _default_kmax_map() -> list[EcnThresholdEntry]:
    # Matches the shipped config.txt defaults: 6 bandwidths (25/40/100/200/400/2400 Gbps)
    # with KMAX thresholds that scale roughly linearly with bandwidth.
    return [
        EcnThresholdEntry(bandwidth_bps=25_000_000_000, threshold=400),
        EcnThresholdEntry(bandwidth_bps=40_000_000_000, threshold=800),
        EcnThresholdEntry(bandwidth_bps=100_000_000_000, threshold=1600),
        EcnThresholdEntry(bandwidth_bps=200_000_000_000, threshold=2400),
        EcnThresholdEntry(bandwidth_bps=400_000_000_000, threshold=3200),
        EcnThresholdEntry(bandwidth_bps=2_400_000_000_000, threshold=3200),
    ]


def _default_kmin_map() -> list[EcnThresholdEntry]:
    return [
        EcnThresholdEntry(bandwidth_bps=25_000_000_000, threshold=100),
        EcnThresholdEntry(bandwidth_bps=40_000_000_000, threshold=200),
        EcnThresholdEntry(bandwidth_bps=100_000_000_000, threshold=400),
        EcnThresholdEntry(bandwidth_bps=200_000_000_000, threshold=600),
        EcnThresholdEntry(bandwidth_bps=400_000_000_000, threshold=800),
        EcnThresholdEntry(bandwidth_bps=2_400_000_000_000, threshold=800),
    ]


def _default_pmax_map() -> list[EcnProbabilityEntry]:
    return [
        EcnProbabilityEntry(bandwidth_bps=b, probability=0.2)
        for b in (
            25_000_000_000,
            40_000_000_000,
            100_000_000_000,
            200_000_000_000,
            400_000_000_000,
            2_400_000_000_000,
        )
    ]


# Python-field -> ns-3 config.txt key mapping. Most fields are just
# name.upper(), but maps and LINK_DOWN need custom serialization. Fields
# NOT in this set are omitted from to_config_txt_dict (they're either
# schema-only metadata like `kind` or structural like `logical_dims`).
_NS3_SCALAR_FIELDS: tuple[str, ...] = (
    "cc_mode",
    "packet_payload_size",
    "buffer_size",
    "error_rate_per_link",
    "enable_qcn",
    "rate_ai",
    "rate_hai",
    "min_rate",
    "alpha_resume_interval",
    "rate_decrease_interval",
    "rp_timer",
    "ewma_gain",
    "fast_recovery_times",
    "clamp_target_rate",
    "has_win",
    "global_t",
    "var_win",
    "fast_react",
    "u_target",
    "mi_thresh",
    "int_multi",
    "pint_log_base",
    "pint_prob",
    "multi_rate",
    "sample_feedback",
    "rate_bound",
    "dctcp_rate_ai",
    "use_dynamic_pfc_threshold",
    "enable_trace",
    "ack_high_prio",
    "l2_back_to_zero",
    "l2_chunk_size",
    "l2_ack_interval",
    "nic_total_pause_time",
    "simulator_stop_time",
    "qlen_mon_start",
    "qlen_mon_end",
)


def _format_scalar(value: Any) -> str:
    """Render one value into a config.txt-compatible string.

    - bool → "1"/"0" (ns-3 reads booleans as 0/1 ints)
    - int/str/other → str()
    - float → repr() to preserve precision (e.g., EWMA_GAIN=0.00390625)
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return repr(value)
    return str(value)


class NS3NetworkConfig(BaseModel):
    """NS-3 packet-level backend config.

    Three structural fields (logical_dims + two paths) plus ~42 typed
    parameters that map 1:1 to keys in ns-3's scratch/config/config.txt.

    `to_config_txt_dict()` renders the typed fields into a `{KEY: value}`
    dict ready to be merged onto a base config.txt via the parser in
    `app.schemas.ns3_config_parser`. `extra_overrides` is an escape
    hatch for keys we don't model explicitly (future config.txt drift).
    """

    kind: Literal["ns3"] = "ns3"

    # ---- structural ----
    logical_dims: list[int] = Field(default_factory=lambda: [8])
    physical_topology_path: str = (
        "extern/network_backend/ns-3/scratch/topology/8_nodes_1_switch_topology.txt"
    )
    mix_config_path: str = "extern/network_backend/ns-3/scratch/config/config.txt"

    # ---- Essentials (always-visible in UI) ----
    cc_mode: CCMode = 12
    packet_payload_size: int = Field(1000, ge=64, le=9216)  # bytes; jumbo-frame ceiling
    buffer_size: int = Field(32, ge=1, le=1024)  # MB, switch per-port
    error_rate_per_link: float = Field(0.0, ge=0.0, le=1.0)
    enable_qcn: bool = True
    rate_ai: str = Field("50Mb/s", pattern=RATE_PATTERN)
    rate_hai: str = Field("100Mb/s", pattern=RATE_PATTERN)
    min_rate: str = Field("100Mb/s", pattern=RATE_PATTERN)

    # ---- Congestion control tuning ----
    alpha_resume_interval: int = Field(1, ge=0)
    rate_decrease_interval: int = Field(4, ge=0)
    rp_timer: int = Field(900, ge=0)
    ewma_gain: float = Field(0.00390625, ge=0.0, le=1.0)
    fast_recovery_times: int = Field(1, ge=0)
    clamp_target_rate: bool = False

    # ---- HPCC / window advanced ----
    has_win: bool = True
    global_t: int = 0
    var_win: bool = True
    fast_react: bool = True
    u_target: float = Field(0.95, ge=0.0, le=1.0)
    mi_thresh: int = Field(0, ge=0)
    int_multi: int = Field(1, ge=0)
    pint_log_base: float = Field(1.05, gt=1.0)
    pint_prob: float = Field(1.0, ge=0.0, le=1.0)
    multi_rate: bool = False
    sample_feedback: bool = False
    rate_bound: bool = True
    dctcp_rate_ai: str = Field("1000Mb/s", pattern=RATE_PATTERN)

    # ---- Global switches ----
    use_dynamic_pfc_threshold: bool = True
    enable_trace: bool = True
    ack_high_prio: bool = False
    l2_back_to_zero: bool = False

    # ---- Packet / link layer ----
    l2_chunk_size: int = Field(4000, ge=0)
    l2_ack_interval: int = Field(1, ge=0)
    nic_total_pause_time: int = Field(0, ge=0)

    # ---- Timing (picoseconds) ----
    simulator_stop_time: float = Field(4e13, gt=0.0)  # 40 seconds
    qlen_mon_start: int = Field(0, ge=0)
    qlen_mon_end: int = Field(20000, ge=0)

    # ---- ECN threshold maps ----
    kmax_map: list[EcnThresholdEntry] = Field(default_factory=_default_kmax_map)
    kmin_map: list[EcnThresholdEntry] = Field(default_factory=_default_kmin_map)
    pmax_map: list[EcnProbabilityEntry] = Field(default_factory=_default_pmax_map)

    # ---- Link control ----
    link_down: LinkDown = Field(default_factory=LinkDown)

    # ---- Escape hatch ----
    # Overlaid last in to_config_txt_dict, so user can override typed
    # defaults here too if they really want. Keys are raw UPPER_SNAKE.
    extra_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_dims(self) -> NS3NetworkConfig:
        if not self.logical_dims:
            raise ValueError("logical_dims must have at least one entry.")
        for d in self.logical_dims:
            if d < 1:
                raise ValueError(f"logical_dims entries must be >= 1 (got {d}).")
        return self

    @model_validator(mode="after")
    def _check_ecn_maps(self) -> NS3NetworkConfig:
        if len(self.kmax_map) != len(self.kmin_map):
            raise ValueError(
                f"kmax_map ({len(self.kmax_map)}) and kmin_map ({len(self.kmin_map)}) "
                "must have the same length; each bandwidth needs both thresholds."
            )
        if len(self.kmax_map) != len(self.pmax_map):
            raise ValueError(
                f"kmax_map ({len(self.kmax_map)}) and pmax_map ({len(self.pmax_map)}) "
                "must have the same length; each bandwidth needs a drop probability."
            )
        # Per-row ordering check: KMIN <= KMAX (otherwise ECN marking is broken).
        for i, (kmax, kmin) in enumerate(zip(self.kmax_map, self.kmin_map, strict=True)):
            if kmax.bandwidth_bps != kmin.bandwidth_bps:
                raise ValueError(
                    f"kmax_map[{i}].bandwidth_bps ({kmax.bandwidth_bps}) must match "
                    f"kmin_map[{i}].bandwidth_bps ({kmin.bandwidth_bps})."
                )
            if kmin.threshold > kmax.threshold:
                raise ValueError(
                    f"ECN row {i} (bw={kmax.bandwidth_bps}): kmin.threshold "
                    f"({kmin.threshold}) must be <= kmax.threshold ({kmax.threshold})."
                )
        return self

    @property
    def total_npus(self) -> int:
        return math.prod(self.logical_dims)

    @property
    def cc_mode_is_experimental(self) -> bool:
        return self.cc_mode in (11, 12)

    def to_logical_topology_json(self) -> str:
        """Serialize to ns-3's logical topology JSON format.

        ns-3 expects strings for each dim; stringify int entries.
        """
        payload = {"logical-dims": [str(d) for d in self.logical_dims]}
        return json.dumps(payload, indent=2) + "\n"

    def to_config_txt_dict(self) -> OrderedDict[str, str]:
        """Render the typed fields as a ``{UPPER_SNAKE_KEY: value_string}`` dict.

        Designed to be fed into ``ns3_config_parser.apply_overrides_dict``
        so the typed values overlay a base config.txt. Field ordering
        follows declaration order (scalars first, then maps, then
        LINK_DOWN, then extra_overrides) so diffs against the base stay
        readable.
        """
        data = self.model_dump()
        out: OrderedDict[str, str] = OrderedDict()
        for fname in _NS3_SCALAR_FIELDS:
            out[fname.upper()] = _format_scalar(data[fname])
        out["KMAX_MAP"] = self._format_ecn_threshold_map(self.kmax_map)
        out["KMIN_MAP"] = self._format_ecn_threshold_map(self.kmin_map)
        out["PMAX_MAP"] = self._format_ecn_probability_map(self.pmax_map)
        out["LINK_DOWN"] = (
            f"{self.link_down.src} {self.link_down.dst} {self.link_down.time}"
        )
        for k, v in self.extra_overrides.items():
            out[k] = v
        return out

    @staticmethod
    def _format_ecn_threshold_map(rows: list[EcnThresholdEntry]) -> str:
        inner = " ".join(f"{r.bandwidth_bps} {r.threshold}" for r in rows)
        return f"{len(rows)} {inner}" if rows else "0"

    @staticmethod
    def _format_ecn_probability_map(rows: list[EcnProbabilityEntry]) -> str:
        inner = " ".join(f"{r.bandwidth_bps} {r.probability}" for r in rows)
        return f"{len(rows)} {inner}" if rows else "0"


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
