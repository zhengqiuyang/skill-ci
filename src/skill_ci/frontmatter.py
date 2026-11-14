"""Minimal YAML-subset parser for SKILL.md frontmatter (stdlib only).

Supported constructs (anything else is reported as a parse note, never guessed):
- flat ``key: value`` scalars; values may be plain or 'single'/"double" quoted
- inline lists ``key: [a, b, c]``
- block lists::

      allowed-tools:
        - Read
        - Bash

- one-level nested mappings under any ``key:`` (notably ``metadata:``)::

      metadata:
        author: someone
        version: "1.0"
        tags: [a, b]
        reviewers:
          - alice

  Entry values reuse the scalar grammar and stay plain strings (no type
  coercion); entry values also support block lists and block scalars
  (``key: >-`` / ``key: |-``), and entry keys may contain ``/`` (observed
  in real host-specific metadata such as ``opencode/autoinvoke``). Entry
  keys are never validated against a whitelist -- rules decide whether
  subkeys matter. Nesting deeper than one level under an entry is allowed
  but stored as a raw string (one stripped line per row), parsed no
  further -- never a crash; each such raw-captured entry is recorded on the
  doc (``SkillDoc.raw_nested``) and reported as FM008 (info) by the rules
  layer.
- folded/literal block scalars (``key: >`` / ``>-`` / ``|`` / ``|-`` / ``>+`` / ``|+``)
- indented plain continuation lines under ``key:`` (folded with spaces)
- full-line ``#`` comments and blank lines

Known limitations (see docs/w1-report.md and docs/w2-report.md): no anchors
or aliases, no inline comments, no flow mappings (``{a: b}``), single
document only, at most one level of nested mappings. A ``key:`` with nothing
under it parses as an empty list so that rules can flag it.
"""

from __future__ import annotations

import re

from .model import SkillDoc

_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_./-]*)\s*:(.*)$")
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


def _indent_width(raw: str) -> int:
    """Leading-whitespace character count (a tab counts as one character).

    Nested-entry depth is compared with this count; tabs in indentation are
    pathological YAML and simply compare by character count.
    """
    width = 0
    for ch in raw:
        if ch in (" ", "\t"):
            width += 1
        else:
            break
    return width


def _peek_shape(block: list[str], index: int) -> str:
    """Classify the first content line at/after ``index`` without consuming it.

    Returns:
    - ``"list"``: indented ``- item`` line -> block list
    - ``"map"``: indented ``key: value`` line -> one-level nested mapping
    - ``"other"``: indented unrecognized line (stays a loud parse note)
    - ``"none"``: dedented content or end of block
    """
    while index < len(block):
        raw = block[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if raw[:1] not in (" ", "\t"):
            return "none"
        if stripped.startswith("- "):
            return "list"
        if _KEY_RE.match(stripped):
            return "map"
        return "other"
    return "none"


def _consume_nested_block_scalar(
    block: list[str],
    index: int,
    target: dict,
    subkey: str,
    entry_indent: int,
    indicator: str,
) -> int:
    """Consume a block scalar used as a nested-map entry value.

    ``index`` points at the ``subkey: >-`` line. Content lines are those
    indented deeper than ``entry_indent``; blank lines belong to the scalar
    until a dedented non-blank line ends it. ``>`` folds to spaces, ``|``
    preserves newlines. Chomping is approximated (``-`` strips, ``+`` keeps
    one trailing newline); the goal is to parse the construct, not to be a
    full YAML implementation.
    """
    j = index + 1
    lines: list[str] = []
    while j < len(block):
        raw = block[j]
        stripped = raw.strip()
        if stripped == "":
            lines.append("")
            j += 1
            continue
        if _indent_width(raw) <= entry_indent:
            break
        lines.append(stripped)
        j += 1

    if indicator.startswith("|"):
        text = "\n".join(lines)
    else:
        text = " ".join(line for line in lines if line)
    if indicator.endswith("+"):
        text = text + ("\n" if text else "")
    else:
        text = text.rstrip()
    target[subkey] = text
    return j


def _consume_map_entry(block: list[str], index: int, doc: SkillDoc, owner_key: str) -> int:
    """Consume one nested-map entry line (``subkey: value``) into
    ``doc.frontmatter[owner_key]`` (a dict). ``index`` points at the entry
    line; the return value is the first line index after the entry.

    Entry value grammar (same as the top level, values stay strings):
    plain/quoted scalars, inline ``[a, b]`` lists, block ``- item`` lists,
    and empty values. Anything indented deeper under an entry with an empty
    value is allowed but captured as a raw string -- no guessing, no crash.
    """
    raw = block[index]
    line_no = index + 2
    match = _KEY_RE.match(raw.strip())
    subkey = match.group(1)
    value_part = match.group(2).strip()
    target: dict = doc.frontmatter[owner_key]
    entry_indent = _indent_width(raw)
    if subkey in target:
        doc.parse_notes.append(
            (line_no, f"duplicate key '{subkey}' under '{owner_key}'")
        )

    if value_part == "":
        # Look ahead past blanks/comments: block list, deeper content, or empty.
        j = index + 1
        while j < len(block):
            raw2 = block[j]
            stripped2 = raw2.strip()
            if not stripped2 or stripped2.startswith("#"):
                j += 1
                continue
            if _indent_width(raw2) <= entry_indent:
                break  # sibling entry or dedent: the value stays empty
            if stripped2.startswith("- "):
                items: list[str] = []
                while j < len(block):
                    raw3 = block[j]
                    stripped3 = raw3.strip()
                    if not stripped3 or stripped3.startswith("#"):
                        j += 1
                        continue
                    if _indent_width(raw3) <= entry_indent:
                        break
                    if stripped3.startswith("- "):
                        items.append(_strip_quotes(stripped3[1:].strip()))
                    else:
                        doc.parse_notes.append(
                            (
                                j + 2,
                                f"unrecognized line inside list value of "
                                f"'{subkey}' under '{owner_key}'",
                            )
                        )
                    j += 1
                target[subkey] = items
                return j
            # Deeper nesting (2+ levels) or any other indented content under an
            # empty entry value: allowed, stored as a raw string, not parsed.
            # FM008 (info) later reports the capability limit per entry.
            raw_lines: list[str] = []
            while j < len(block):
                raw3 = block[j]
                stripped3 = raw3.strip()
                if not stripped3 or stripped3.startswith("#"):
                    j += 1
                    continue
                if _indent_width(raw3) > entry_indent:
                    raw_lines.append(stripped3)
                    j += 1
                    continue
                break
            target[subkey] = "\n".join(raw_lines)
            doc.raw_nested.append((line_no, f"{owner_key}.{subkey}"))
            return j
        target[subkey] = ""
        return j

    if value_part in _BLOCK_SCALAR_INDICATORS:
        return _consume_nested_block_scalar(
            block, index, target, subkey, entry_indent, value_part
        )

    if value_part.startswith("[") and value_part.endswith("]"):
        target[subkey] = _split_inline_list(value_part)
    else:
        target[subkey] = _strip_quotes(value_part)
    return index + 1


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
    pending_mode: str | None = None  # "list" | "scalar" | "map"
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
            if pending_mode == "map":
                if (
                    indented
                    and not stripped.startswith("- ")
                    and _KEY_RE.match(stripped)
                ):
                    index = _consume_map_entry(block, index, doc, pending_key)
                    continue
                # dedented or unrecognized line: the nested map is finished and
                # the current line is (re)processed at the top level below
                pending_key = None
                pending_mode = None
            elif stripped.startswith("- ") and pending_mode == "list":
                current = doc.frontmatter[pending_key]
                if isinstance(current, list):
                    current.append(_strip_quotes(stripped[1:].strip()))
                index += 1
                continue
            elif indented and pending_mode == "scalar" and not stripped.startswith("- "):
                doc.frontmatter[pending_key] = (
                    str(doc.frontmatter[pending_key]) + " " + stripped
                ).strip()
                index += 1
                continue
            elif indented and pending_mode == "list":
                doc.parse_notes.append(
                    (line_no, f"indented non-list line under list key '{pending_key}'")
                )
                index += 1
                continue
            else:
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
            shape = _peek_shape(block, index + 1)
            if shape == "map":
                doc.frontmatter[key] = {}
                pending_mode = "map"
            else:
                # list items, unrecognized continuation (loud note), or nothing
                doc.frontmatter[key] = []
                pending_mode = "list"
            pending_key = key
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
