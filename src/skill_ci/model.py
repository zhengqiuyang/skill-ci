"""Core data structures shared by the parser, rules and renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tokens import estimate_tokens

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITIES = (SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)


@dataclass(frozen=True)
class Finding:
    """One lint result.

    ``line`` is 1-based; 0 means the finding is not line-specific
    (whole-file or whole-target structural problems).
    """

    rule_id: str
    severity: str
    file: str
    line: int
    message: str
    fix_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


@dataclass
class SkillDoc:
    """One parsed SKILL.md file."""

    rel_path: str = ""
    dir_name: str = ""
    text: str = ""
    has_frontmatter: bool = False
    frontmatter: dict[str, Any] = field(default_factory=dict)
    key_lines: dict[str, int] = field(default_factory=dict)
    parse_notes: list[tuple[int, str]] = field(default_factory=list)
    body: str = ""
    body_start_line: int = 1
    fm_close_line: int | None = None

    @property
    def name(self) -> str | None:
        value = self.frontmatter.get("name")
        return value if isinstance(value, str) else None

    @property
    def description(self) -> str | None:
        value = self.frontmatter.get("description")
        return value if isinstance(value, str) else None

    @property
    def body_tokens(self) -> int:
        """Script-weighted token estimate (single shared口径; see skill_ci.tokens).

        Pure ASCII stays exactly ``len(text) // 4`` (W1 behaviour); CJK
        characters count ~1 token each instead of 1/4 (W1 underestimated
        Chinese content by roughly 4x).
        """
        return estimate_tokens(self.body)
