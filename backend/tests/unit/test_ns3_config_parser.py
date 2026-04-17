"""Unit tests for the ns-3 config.txt parser / renderer."""

from __future__ import annotations

from collections import OrderedDict

from app.schemas.ns3_config_parser import (
    apply_overrides_dict,
    parse_config_txt,
    write_config_txt,
)


class TestParseConfigTxt:
    def test_simple_key_value(self):
        parsed = parse_config_txt("ENABLE_QCN 1\nPACKET_PAYLOAD_SIZE 1000\n")
        assert parsed == OrderedDict(ENABLE_QCN="1", PACKET_PAYLOAD_SIZE="1000")

    def test_blank_lines_dropped(self):
        parsed = parse_config_txt("ENABLE_QCN 1\n\n\nPACKET_PAYLOAD_SIZE 1000\n")
        assert list(parsed) == ["ENABLE_QCN", "PACKET_PAYLOAD_SIZE"]

    def test_preserves_order(self):
        src = "A 1\nB 2\nC 3\n"
        parsed = parse_config_txt(src)
        assert list(parsed) == ["A", "B", "C"]

    def test_map_values_preserved_verbatim(self):
        # Map values contain many whitespace-separated tokens; must stay
        # as a single string so the schema layer can parse them itself.
        src = "KMAX_MAP 3 25000000000 400 50000000000 800 100000000000 1600\n"
        parsed = parse_config_txt(src)
        assert parsed["KMAX_MAP"] == "3 25000000000 400 50000000000 800 100000000000 1600"

    def test_comment_lines_dropped(self):
        src = "# this is a comment\nA 1\n# and another\nB 2\n"
        parsed = parse_config_txt(src)
        assert parsed == OrderedDict(A="1", B="2")

    def test_bare_key_becomes_empty_value(self):
        parsed = parse_config_txt("STANDALONE_FLAG\nA 1\n")
        assert parsed["STANDALONE_FLAG"] == ""
        assert parsed["A"] == "1"

    def test_trailing_whitespace_trimmed(self):
        parsed = parse_config_txt("A 1   \nB 2\t\n")
        assert parsed == OrderedDict(A="1", B="2")

    def test_empty_input_returns_empty_dict(self):
        assert parse_config_txt("") == OrderedDict()
        assert parse_config_txt("\n\n\n") == OrderedDict()


class TestApplyOverridesDict:
    def test_existing_key_updated_in_place(self):
        base = OrderedDict([("A", "1"), ("B", "2"), ("C", "3")])
        merged = apply_overrides_dict(base, {"B": "99"})
        assert merged == OrderedDict([("A", "1"), ("B", "99"), ("C", "3")])

    def test_new_keys_appended_in_override_order(self):
        base = OrderedDict([("A", "1")])
        merged = apply_overrides_dict(base, {"X": "10", "Y": "20"})
        assert list(merged) == ["A", "X", "Y"]

    def test_base_not_mutated(self):
        base = OrderedDict([("A", "1")])
        apply_overrides_dict(base, {"A": "99", "B": "2"})
        assert base == OrderedDict([("A", "1")])

    def test_mixed_update_and_append(self):
        base = OrderedDict([("A", "1"), ("B", "2")])
        merged = apply_overrides_dict(base, {"B": "99", "C": "3"})
        assert merged == OrderedDict([("A", "1"), ("B", "99"), ("C", "3")])


class TestWriteConfigTxt:
    def test_trailing_newline(self):
        out = write_config_txt(OrderedDict([("A", "1")]))
        assert out == "A 1\n"

    def test_bare_key_emitted_without_space(self):
        out = write_config_txt(OrderedDict([("FLAG", ""), ("A", "1")]))
        assert out == "FLAG\nA 1\n"

    def test_empty_dict_still_emits_newline(self):
        # A minimal valid file is one newline.
        assert write_config_txt(OrderedDict()) == "\n"


class TestRoundtrip:
    def test_real_config_roundtrip_preserves_content(self):
        src = (
            "ENABLE_QCN 1\n"
            "USE_DYNAMIC_PFC_THRESHOLD 1\n"
            "\n"
            "PACKET_PAYLOAD_SIZE 1000\n"
            "\n"
            "TOPOLOGY_FILE ../../scratch/topology/8_nodes_1_switch_topology.txt\n"
            "CC_MODE 12\n"
            "KMAX_MAP 3 25000000000 400 50000000000 800 100000000000 1600\n"
        )
        parsed = parse_config_txt(src)
        rendered = write_config_txt(parsed)
        # Blank lines are collapsed but every key-value pair survives.
        assert "ENABLE_QCN 1" in rendered
        assert "CC_MODE 12" in rendered
        assert (
            "KMAX_MAP 3 25000000000 400 50000000000 800 100000000000 1600"
            in rendered
        )
        # Second-pass parse equals first-pass parse (fixed point).
        assert parse_config_txt(rendered) == parsed

    def test_unknown_keys_passthrough(self):
        # Simulates a future ns-3 version adding a new key the schema
        # doesn't know about.
        src = "CC_MODE 3\nMY_FUTURE_KEY some-value-with-dashes\n"
        parsed = parse_config_txt(src)
        merged = apply_overrides_dict(parsed, {"CC_MODE": "1"})
        rendered = write_config_txt(merged)
        assert "CC_MODE 1" in rendered
        assert "MY_FUTURE_KEY some-value-with-dashes" in rendered
