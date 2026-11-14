"""Minimal YAML-subset parser for SKILL.md frontmatter (stdlib only).

Supported constructs (anything else is reported as a parse note, never guessed):
- flat ``key: value`` scalars; values may be plain or 'single'/"double" quoted
- inline lists ``key: [a, b, c]``
- block lists::

      allowed-tools:
        - Read
        - Bash

- folded/literal block scalars (``key: >`` / ``>-`` / ``|`` / ``|-`` / ``>+`` / ``|+``)
- indented plain continuation lines under ``key:`` (folded with spaces)
- full-line ``#`` comments and blank lines

Known limitations (see docs/w1-report.md): no nested mappings, no anchors or
aliases, no inline comments, single document only. A ``key:`` with nothing
under it parses as an empty list so that rules can flag it.
"""

from __future__ import annotations

import re

from .model import SkillDoc

_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)\s*:(.*)$")
_BLOCK_SCALAR_INDICATORS = (">", ">-", ">+", "|", "|-", "|+")


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _split_inline_list(raw: str) -> list[str]:
    inner = raw[1:-1].strip()
    if not inner:
        return []
    return [_strip_quotes(part.strip()) for part in inner.split(",") if part.strip()]


def parse_skill_text(text: str) -> SkillDoc:
    """Parse SKILL.md text into a :class:`SkillDoc` (never raises on content)."""
    doc = SkillDoc(text=text)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        doc.body = text
        doc.body_start_line = 1
        return doc
    close_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            close_idx = idx
            break
    if close_idx is None:
        doc.body = text
        doc.body_start_line = 1
        doc.parse_notes.append((1, "frontmatter opens with '---' but is never closed"))
        return doc
    doc.has_frontmatter = True
    doc.fm_close_line = close_idx + 1
    doc.body = "\n".join(lines[close_idx + 1:])
    doc.body_start_line = close_idx + 2
    _parse_block(lines[1:close_idx], doc)
    return doc


def _parse_block(block: list[str], doc: SkillDoc) -> None:
    """Parse frontmatter lines. File line number of ``block[i]`` is ``i + 2``
    (file line 1 is the opening ``---``)."""
    index = 0
    pending_key: str | None = None
    pending_mode: str | None = None  # "list" | "scalar"
    seen_keys: set[str] = set()
    while index < len(block):
        raw = block[index]
        line_no = index + 2
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        indented = raw[:1] in (" ", "\t")

        if pending_key is not None:
            if stripped.startswith("- ") and pending_mode == "list":
                current = doc.frontmatter[pending_key]
                if isinstance(current, list):
                    current.append(_strip_quotes(stripped[1:].strip()))
                index += 1
                continue
            if indented and pending_mode == "scalar" and not stripped.startswith("- "):
                doc.frontmatter[pending_key] = (
                    str(doc.frontmatter[pending_key]) + " " + stripped
                ).strip()
                index += 1
                continue
            if indented and pending_mode == "list":
                doc.parse_notes.append(
                    (line_no, f"indented non-list line under list key '{pending_key}'")
                )
                index += 1
                continue
            # dedented content: the pending key is finished
            pending_key = None
            pending_mode = None

        match = _KEY_RE.match(stripped)
        if not match:
            doc.parse_notes.append(
                (line_no, "unrecognized frontmatter line (expected 'key: value')")
            )
            index += 1
            continue
        key = match.group(1)
        value_part = match.group(2).strip()
        if key in seen_keys:
            doc.parse_notes.append((line_no, f"duplicate frontmatter key '{key}'"))
        seen_keys.add(key)
        doc.key_lines.setdefault(key, line_no)

        if value_part == "":
            doc.frontmatter[key] = []
            pending_key = key
            pending_mode = "list"
            index += 1
            continue
        if value_part in _BLOCK_SCALAR_INDICATORS:
            doc.frontmatter[key] = ""
            pending_key = key
            pending_mode = "scalar"
            index += 1
            continue
        pending_key = None
        pending_mode = None
        if value_part.startswith("[") and value_part.endswith("]"):
            doc.frontmatter[key] = _split_inline_list(value_part)
        else:
            doc.frontmatter[key] = _strip_quotes(value_part)
        index += 1
