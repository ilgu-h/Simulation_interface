"""Unit tests for ns-3 output file parsers.

Uses in-memory fixtures (tmp_path) rather than real ns-3 runs so the
suite doesn't depend on the binary being built.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers.ns3 import (
    as_records,
    ip_hex_to_node_id,
    parse_fct,
    parse_pfc,
    parse_qlen,
    summarize_links,
)

# ---------- fct.txt ---------------------------------------------------------


class TestParseFct:
    def test_empty_file_returns_empty(self, tmp_path: Path):
        p = tmp_path / "fct.txt"
        p.write_text("")
        assert parse_fct(p) == []

    def test_missing_file_returns_empty(self, tmp_path: Path):
        # No error; callers don't need to pre-check existence.
        assert parse_fct(tmp_path / "does_not_exist.txt") == []

    def test_parses_sample_row(self, tmp_path: Path):
        # Matches real qp_finish_print_log output from entry.h L249.
        p = tmp_path / "fct.txt"
        p.write_text("0b000001 0b000101 10000 100 32768 10 2711 2727\n")
        rows = parse_fct(p)
        assert len(rows) == 1
        assert rows[0].sip_hex == "0b000001"
        assert rows[0].dip_hex == "0b000101"
        assert rows[0].sport == 10000
        assert rows[0].dport == 100
        assert rows[0].size_bytes == 32768
        assert rows[0].start_time_ns == 10
        assert rows[0].fct_ns == 2711
        assert rows[0].standalone_fct_ns == 2727

    def test_skips_malformed_rows(self, tmp_path: Path):
        p = tmp_path / "fct.txt"
        p.write_text(
            # Valid
            "0b000001 0b000101 10000 100 32768 10 2711 2727\n"
            # Too few columns — dropped silently
            "0b000002 0b000202 10000\n"
            # Non-numeric — dropped
            "0b000003 0b000303 10000 100 BAD 10 2711 2727\n"
            # Valid
            "0b000004 0b000404 10000 100 65536 20 5000 5100\n"
        )
        rows = parse_fct(p)
        assert len(rows) == 2
        assert rows[0].dip_hex == "0b000101"
        assert rows[1].dip_hex == "0b000404"


# ---------- qlen.txt --------------------------------------------------------


class TestParseQlen:
    def test_single_line_expands_to_per_port_samples(self, tmp_path: Path):
        # Real format: "time T SW j port1 bytes1 j port2 bytes2 ..."
        p = tmp_path / "qlen.txt"
        p.write_text("time 3900 8 j 1 1036 j 2 2048 j 3 512\n")
        samples = parse_qlen(p)
        assert len(samples) == 3
        assert samples[0].time_ns == 3900
        assert samples[0].switch_id == 8
        assert samples[0].port == 1
        assert samples[0].bytes_ == 1036
        assert samples[2].port == 3
        assert samples[2].bytes_ == 512

    def test_multiple_lines_preserve_time_order(self, tmp_path: Path):
        p = tmp_path / "qlen.txt"
        p.write_text(
            "time 100 4 j 1 1000\n"
            "time 200 4 j 1 1500\n"
            "time 300 5 j 1 2000\n"
        )
        samples = parse_qlen(p)
        assert [s.time_ns for s in samples] == [100, 200, 300]
        assert [s.switch_id for s in samples] == [4, 4, 5]

    def test_skips_lines_without_time_token(self, tmp_path: Path):
        p = tmp_path / "qlen.txt"
        p.write_text(
            "garbage line\n"
            "time 100 4 j 1 1000\n"
            "\n"
            "# comment-style noise\n"
        )
        samples = parse_qlen(p)
        assert len(samples) == 1
        assert samples[0].time_ns == 100

    def test_missing_file_returns_empty(self, tmp_path: Path):
        assert parse_qlen(tmp_path / "qlen.txt") == []

    def test_trailing_partial_triplet_is_dropped(self, tmp_path: Path):
        """A crash-terminated ns-3 can leave a half-written triplet at EOL.

        The parser must drop the partial triplet rather than crash or
        misparse — the preceding complete triplets are still usable data.
        """
        p = tmp_path / "qlen.txt"
        # "j 1 1000" is complete; "j 2" is a partial triplet missing bytes.
        p.write_text("time 100 4 j 1 1000 j 2\n")
        samples = parse_qlen(p)
        assert len(samples) == 1
        assert samples[0].port == 1
        assert samples[0].bytes_ == 1000


# ---------- pfc.txt ---------------------------------------------------------


class TestParsePfc:
    def test_empty_file_is_not_an_error(self, tmp_path: Path):
        # The common case — healthy workloads never trigger PFC.
        p = tmp_path / "pfc.txt"
        p.write_text("")
        assert parse_pfc(p) == []

    def test_parses_pause_and_resume(self, tmp_path: Path):
        p = tmp_path / "pfc.txt"
        p.write_text("1500 3 2 0\n2000 3 2 1\n")
        events = parse_pfc(p)
        assert len(events) == 2
        assert events[0].time_ns == 1500
        assert events[0].node_id == 3
        assert events[0].port == 2
        assert events[0].type_code == 0
        assert events[0].kind == "pause"
        assert events[1].kind == "resume"


# ---------- ip_hex_to_node_id -----------------------------------------------


class TestIpHexToNodeId:
    def test_extracts_low_24_bits(self):
        # 0x0b000001 → node 1; ASTRA-sim encodes node id in low 24 bits.
        assert ip_hex_to_node_id("0b000001") == 1
        assert ip_hex_to_node_id("0b000101") == 0x000101
        assert ip_hex_to_node_id("0bffffff") == 0xFFFFFF


# ---------- summarize_links -------------------------------------------------


class TestSummarizeLinks:
    def test_aggregates_by_src_dst_pair(self, tmp_path: Path):
        from app.parsers.ns3 import FlowRecord

        flows = [
            FlowRecord("0b000001", "0b000101", 10000, 100, 1024, 10, 1000, 1100),
            FlowRecord("0b000001", "0b000101", 10001, 100, 2048, 20, 1500, 1600),
            FlowRecord("0b000002", "0b000202", 10000, 100, 512, 30, 800, 850),
        ]
        stats = summarize_links(flows)
        assert len(stats) == 2

        # Sorted by total_bytes desc: (1->101) 3072 > (2->202) 512
        hot = stats[0]
        assert (hot.sip_hex, hot.dip_hex) == ("0b000001", "0b000101")
        assert hot.flow_count == 2
        assert hot.total_bytes == 3072
        assert hot.avg_fct_ns == pytest.approx(1250.0)
        assert hot.max_fct_ns == 1500

    def test_empty_input_returns_empty(self):
        assert summarize_links([]) == []


# ---------- as_records helper -----------------------------------------------


def test_as_records_converts_to_plain_dicts(tmp_path: Path):
    """The results API serializes dicts directly, so as_records() unlocks
    passing parser output straight to JSONResponse."""
    p = tmp_path / "fct.txt"
    p.write_text("0b000001 0b000101 10000 100 32768 10 2711 2727\n")
    records = as_records(parse_fct(p))
    assert isinstance(records, list)
    assert isinstance(records[0], dict)
    assert records[0]["sip_hex"] == "0b000001"
    assert records[0]["size_bytes"] == 32768
