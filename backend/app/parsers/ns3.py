"""Parsers for ns-3 packet-level output files.

The ns-3 backend writes four text output files per run (path keys live in
``config.txt``):

- ``fct.txt``  — one row per completed RDMA queue pair (flow).
  Format (from ``astra-sim/network_frontend/ns3/entry.h::qp_finish_print_log``)::

      sip(%08x) dip(%08x) sport dport size_bytes start_time_ns fct_ns standalone_fct_ns

- ``qlen.txt`` — switch-buffer samples.
  Format (from ``extern/network_backend/ns-3/scratch/common.h::monitor_buffer``)::

      time <ns> <switch_node_id> j <port> <bytes> [j <port> <bytes>]...

  A line is only emitted when at least one port on a switch has ≥1000 bytes
  queued at the sample tick; idle switches produce no output.

- ``pfc.txt``  — per-port pause/resume events (empty for well-behaved
  workloads).

- ``mix.tr``   — binary packet trace. **Not parsed here** — it's ns-3's
  native PCAP-style trace and needs ``ns-3``'s own tooling. Surfacing it
  through the results API is future work.

Parsers are stdlib-only (no pandas) so they stay cheap to import and easy
to unit-test. Callers that want tabular output can convert the returned
dataclasses with ``dataclasses.asdict`` and feed into pandas themselves.
All parsers return an empty list if the input file is missing — runs
with no flows (e.g. workloads below the simulator's reporting threshold)
are not errors.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class FlowRecord:
    """One completed RDMA queue pair.

    ``sip_hex`` / ``dip_hex`` are the raw 32-bit IPs as printed by ns-3
    (``%08x``). Use :func:`ip_hex_to_node_id` to map them to a logical
    node id when you need the topology view.
    """

    sip_hex: str
    dip_hex: str
    sport: int
    dport: int
    size_bytes: int
    start_time_ns: int
    fct_ns: int
    standalone_fct_ns: int


@dataclass(frozen=True)
class QueueSample:
    """One switch-port queue-length sample.

    ``time_ns`` is the simulator timestamp; ``switch_id`` is the ns-3
    node index of the switch; ``port`` is the device index on that
    switch (1-based). ``bytes_`` is the aggregate egress byte count
    across all priorities at sample time.
    """

    time_ns: int
    switch_id: int
    port: int
    bytes_: int


@dataclass(frozen=True)
class PfcEvent:
    """One PFC pause/resume event.

    ns-3's PFC writer in common.h emits ``time nodeId port type`` where
    type is 0 for pause and 1 for resume. Keep the raw int on the
    record and expose a string alias via :attr:`kind`.
    """

    time_ns: int
    node_id: int
    port: int
    type_code: int

    @property
    def kind(self) -> str:
        return "pause" if self.type_code == 0 else "resume"


@dataclass(frozen=True)
class LinkStat:
    """Aggregate flow stats for one (src, dst) pair.

    Derived by :func:`summarize_links` from :class:`FlowRecord` rows —
    the raw ns-3 output doesn't emit per-link stats directly, but
    summing flow sizes and FCTs per endpoint pair is a good proxy for
    offered load and link hotness.
    """

    sip_hex: str
    dip_hex: str
    flow_count: int
    total_bytes: int
    avg_fct_ns: float
    max_fct_ns: int


def ip_hex_to_node_id(ip_hex: str) -> int:
    """Map an ns-3 IP (``%08x``) to its node id.

    ASTRA-sim's ns-3 frontend encodes node id in the low 24 bits of the
    IP (``0x0b000001`` → node 1, ``0x0b000101`` → node 257 on multi-pod
    topologies). We mirror that convention here. Returns the raw low-24
    value; callers can re-map if their topology uses a different scheme.
    """
    return int(ip_hex, 16) & 0x00FFFFFF


# ---------- fct.txt ---------------------------------------------------------


def parse_fct(path: Path) -> list[FlowRecord]:
    """Parse fct.txt into a list of :class:`FlowRecord`.

    Silently skips malformed rows (too few fields, non-numeric) so one
    truncated line — e.g. mid-write when the sim aborted — doesn't
    poison the whole result set.
    """
    if not path.exists():
        return []
    rows: list[FlowRecord] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 8:
            continue
        try:
            rows.append(
                FlowRecord(
                    sip_hex=parts[0],
                    dip_hex=parts[1],
                    sport=int(parts[2]),
                    dport=int(parts[3]),
                    size_bytes=int(parts[4]),
                    start_time_ns=int(parts[5]),
                    fct_ns=int(parts[6]),
                    standalone_fct_ns=int(parts[7]),
                )
            )
        except ValueError:
            continue
    return rows


# ---------- qlen.txt --------------------------------------------------------


def parse_qlen(path: Path) -> list[QueueSample]:
    """Parse qlen.txt into a flat list of :class:`QueueSample`.

    Each source line expands into N samples (one per ``j port bytes``
    triplet). The returned list is in file order — time-ordered by
    virtue of how ns-3 writes the file.
    """
    if not path.exists():
        return []
    samples: list[QueueSample] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        # Minimum valid line: "time T SW" (no j-triplets → no samples).
        if len(parts) < 3 or parts[0] != "time":
            continue
        try:
            time_ns = int(parts[1])
            switch_id = int(parts[2])
        except ValueError:
            continue
        # Walk the (j, port, bytes) triplets. ns-3 uses 'j' as a literal
        # separator token, so each triplet is 3 tokens starting with 'j'.
        # A trailing partial triplet (crash mid-write) is dropped — the
        # `i + 3 <= len(parts)` guard ensures we never index past the end.
        i = 3
        while i + 3 <= len(parts):
            if parts[i] != "j":
                break
            try:
                port = int(parts[i + 1])
                bytes_ = int(parts[i + 2])
            except ValueError:
                break
            samples.append(
                QueueSample(
                    time_ns=time_ns, switch_id=switch_id, port=port, bytes_=bytes_
                )
            )
            i += 3
    return samples


# ---------- pfc.txt ---------------------------------------------------------


def parse_pfc(path: Path) -> list[PfcEvent]:
    """Parse pfc.txt into a list of :class:`PfcEvent`.

    Returns an empty list when there are no PFC events (the common case
    for workloads that don't saturate link capacity). File format per
    ns-3's ``scratch/common.h``: ``time nodeId port type``.
    """
    if not path.exists():
        return []
    events: list[PfcEvent] = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        try:
            events.append(
                PfcEvent(
                    time_ns=int(parts[0]),
                    node_id=int(parts[1]),
                    port=int(parts[2]),
                    type_code=int(parts[3]),
                )
            )
        except ValueError:
            continue
    return events


# ---------- derived: per-link aggregation -----------------------------------


def summarize_links(flows: list[FlowRecord]) -> list[LinkStat]:
    """Aggregate flows by (sip, dip) pair.

    For the heatmap UI: the (src, dst) communication matrix with flow
    count, total bytes, and FCT statistics per pair. Result is sorted
    by total_bytes descending so hot pairs surface first.
    """
    buckets: dict[tuple[str, str], list[FlowRecord]] = {}
    for f in flows:
        buckets.setdefault((f.sip_hex, f.dip_hex), []).append(f)
    stats: list[LinkStat] = []
    for (sip, dip), group in buckets.items():
        fcts = [f.fct_ns for f in group]
        stats.append(
            LinkStat(
                sip_hex=sip,
                dip_hex=dip,
                flow_count=len(group),
                total_bytes=sum(f.size_bytes for f in group),
                avg_fct_ns=sum(fcts) / len(fcts),
                max_fct_ns=max(fcts),
            )
        )
    stats.sort(key=lambda s: s.total_bytes, reverse=True)
    return stats


def as_records(items: list) -> list[dict]:
    """Convert a list of dataclasses to JSON-serializable dicts.

    Convenience for the results API: FastAPI can serialize dicts
    natively, dataclasses need asdict() first.
    """
    return [asdict(x) for x in items]


__all__ = [
    "FlowRecord",
    "LinkStat",
    "PfcEvent",
    "QueueSample",
    "as_records",
    "ip_hex_to_node_id",
    "parse_fct",
    "parse_pfc",
    "parse_qlen",
    "summarize_links",
]
