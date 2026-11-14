"""Scan a target directory and produce the unified findings list."""

from __future__ import annotations

from pathlib import Path

from . import rules
from .discover import find_skill_files
from .frontmatter import parse_skill_text
from .model import Finding, SkillDoc


def lint_path(root: Path) -> tuple[list[SkillDoc], list[Finding]]:
    """Lint ``root`` and return (parsed skill docs, sorted findings)."""
    findings: list[Finding] = []
    files = find_skill_files(root)
    if not files:
        findings.append(
            Finding(
                "STRUCT001",
                "error",
                str(root),
                0,
                "no SKILL.md files found under the target directory",
                "Point skill-lint at a directory containing skills as <skill-name>/SKILL.md.",
            )
        )
        return [], findings

    docs: list[SkillDoc] = []
    for path in files:
        try:
            rel_path = path.relative_to(root).as_posix()
        except ValueError:
            rel_path = path.as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            findings.append(
                Finding("STRUCT002", "error", rel_path, 0, f"unreadable SKILL.md: {exc}", None)
            )
            continue
        doc = parse_skill_text(text)
        doc.rel_path = rel_path
        doc.dir_name = path.parent.name
        docs.append(doc)
        rules.check_frontmatter(doc, findings)
        rules.check_description(doc, findings)
        rules.check_tokens(doc, findings)
        rules.check_security(doc, findings)

    rules.check_duplicates(docs, findings)
    findings.sort(key=lambda f: (f.file, f.line, f.rule_id))
    return docs, findings
