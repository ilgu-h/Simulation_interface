"""Round-trip utilities for ns-3's plain-text ``config.txt`` format.

The file format is simple but unforgiving:

- One ``KEY VALUE`` pair per line, whitespace-separated.
- Blank lines are allowed (and preserved as structural separators).
- **Comments are NOT supported by the ns-3 parser** — we refuse to emit
  any line starting with ``#``; on parse we ignore them but log a warning
  so round-trips stay safe.
- Keys are case-sensitive UPPER_SNAKE_CASE. Unknown keys are silently
  ignored by ns-3, so we preserve them as-is through parse/render.
- Map-style values (``KMAX_MAP N bw1 v1 bw2 v2 ...``) are stored as the
  full post-key string; the schema layer parses them into structured
  types when needed.

Typical usage in the orchestrator:

    base = parse_config_txt(base_file.read_text())
    merged = apply_overrides_dict(base, user_overrides_dict)
    out_path.write_text(write_config_txt(merged))

Overrides from a typed ``NS3NetworkConfig`` are produced by the schema's
own ``to_config_txt_dict()`` method and merged via ``apply_overrides_dict``.
"""

from __future__ import annotations

from collections import OrderedDict


def parse_config_txt(text: str) -> OrderedDict[str, str]:
    """Parse ns-3 ``config.txt`` content into an ordered ``KEY -> value`` dict.

    Preserves original ordering so round-trips stay diff-friendly. Blank
    lines are dropped (ns-3 tolerates them and they carry no semantics).
    Comment lines starting with ``#`` are dropped with no diagnostic — the
    caller is expected to not feed commented input since ns-3 itself
    can't handle it.
    """
    out: OrderedDict[str, str] = OrderedDict()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Split on first whitespace run — the remainder may contain
        # further whitespace (maps carry many tokens).
        parts = line.split(None, 1)
        if len(parts) == 1:
            # Bare key with no value — preserve as empty string so the
            # round-trip emits it back out unchanged.
            out[parts[0]] = ""
        else:
            key, value = parts
            out[key] = value.rstrip()
    return out


def apply_overrides_dict(
    base: OrderedDict[str, str], overrides: dict[str, str]
) -> OrderedDict[str, str]:
    """Merge ``overrides`` onto ``base``.

    Keys present in ``base`` are updated in place (preserving original
    line order). Keys present only in ``overrides`` are appended in the
    order ``overrides`` provides them. Returns a new dict; inputs are
    not mutated.
    """
    merged: OrderedDict[str, str] = OrderedDict(base)
    for key, value in overrides.items():
        merged[key] = value
    return merged


def write_config_txt(merged: OrderedDict[str, str]) -> str:
    """Render a merged config dict back to ``config.txt`` text.

    Emits one ``KEY VALUE`` line per entry, preserving ``merged``'s order.
    A bare key with empty value is rendered as ``KEY`` (no trailing
    space) to keep round-trips byte-identical in the rare cases they
    appear.

    Always ends with a single trailing newline.
    """
    lines: list[str] = []
    for key, value in merged.items():
        if value == "":
            lines.append(key)
        else:
            lines.append(f"{key} {value}")
    return "\n".join(lines) + "\n"
