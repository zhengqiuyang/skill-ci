"""Lint rules for SKILL.md files. Every finding carries rule_id/file/line."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .model import SEVERITY_INFO, SEVERITY_WARNING, Finding, SkillDoc

# ---------------------------------------------------------------------------
# Thresholds (all documented in docs/w1-report.md)
# ---------------------------------------------------------------------------
MAX_BODY_TOKENS = 5000         # TK001 warning: body above ~5k estimated tokens
HARD_BODY_TOKENS = 15000       # TK002 error: body must be split / loaded on demand
MAX_DESCRIPTION_CHARS = 1024   # DQ004 error: SKILL.md spec limit
MIN_DESCRIPTION_CHARS = 20     # DQ001 warning: too short to trigger reliably
MAX_NAME_LEN = 64              # FM003 error: SKILL.md spec limit
DESC_SIMILAR_RATIO = 0.85      # DUP002 warning: SequenceMatcher ratio, lowercased text
DESC_JACCARD = 0.60            # DUP003 warning: token Jaccard over [a-z0-9]{3,}

NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

# Claude Code frontmatter extension keys（2026-11 实测于公开 skill 仓库：
# Jeffallan/claude-skills、jwilger/agent-skills）. Real skills legitimately
# carry these keys, so they are accepted (no FM007) in addition to the
# SKILL.md spec keys below. Kept as a separate frozenset so the source stays
# documented and the extension surface stays reviewable.
CLAUDE_CODE_EXTENSION_KEYS = frozenset({
    "effort",
    "compatibility",
    "context",
    "argument-hint",
    "user-invocable",
    "disable-model-invocation",
})

KNOWN_FRONTMATTER_KEYS = {
    "name",
    "description",
    "when_to_use",
    "allowed-tools",
    "license",
    "metadata",
} | CLAUDE_CODE_EXTENSION_KEYS

# ---------------------------------------------------------------------------
# Noise-policy constants (documented, configurable; no repo-specific names).
# ---------------------------------------------------------------------------
# SEC002: a credential-shaped string that is clearly a placeholder,
# documentation example or test value is downgraded from warning to info.
# Docs, tutorials and test fixtures legitimately contain such strings; they
# are not real secret leakage. Checked against the matched credential value
# (or the whole match for key-less patterns), lowercased.
SEC002_PLACEHOLDER_PREFIXES = (
    "your-",        # your-password-here / your_api_key
    "your_",
    "xxx",          # xxx, xxxx-xxxx (see also the substring check below)
    "dummy",        # dummy-secret
    "sample",       # sample-credential
    "placeholder",  # placeholder-value
    "changeme",     # changeme / changeme-123
    "change-me",    # change-me-please
    "test-",        # test-password
    "test_",        # test_secret
    "${",           # ${DB_PASSWORD} env-var template reference
)
SEC002_PLACEHOLDER_VALUES = frozenset({
    "xxx",
    "xxxx",
    "test",
    "dummy",
    "sample",
    "placeholder",
    "changeme",
    "change-me",
    "redacted",
    "none",
    "null",
    "n/a",
    "password",
    "password123",
    "secret",
    "token",
    "<placeholder>",
})
# FM004: a name/directory mismatch under a scaffold-style directory is
# expected content (the directory is a template for skills, not a skill
# itself), so the finding is downgraded from warning to info. Matches any
# directory component of the repo-relative skill path, case-insensitively.
FM004_TEMPLATE_DIR_MARKERS = frozenset({
    "template",
    "templates",
    "_template",
    "_templates",
    "example",
    "examples",
    "sample",
    "samples",
    "scaffold",
    "scaffolds",
    "boilerplate",
})

GENERIC_PHRASES = (
    "helps with",
    "help with",
    "useful for",
    "various tasks",
    "general purpose",
    "general-purpose",
    "miscellaneous",
    "all things",
    "everything about",
    "and more",
)
TRIGGER_HINTS = (
    "use when",
    "use this when",
    "when to use",
    "use whenever",
    "should be used when",
    "if the user",
    "when the user",
    # CJK equivalents (W2): a Chinese/Japanese description that says when to
    # use the skill should not be flagged for lacking English guidance.
    "当用户",
    "当需要",
    "适用于",
    "何时使用",
)

RULE_CATALOG: dict[str, str] = {
    "FM001": "frontmatter missing, unclosed, or contains lines outside the supported YAML subset",
    "FM002": "frontmatter is missing the required 'name' key",
    "FM003": "'name' must be lowercase [a-z0-9-], max 64 chars, no leading/trailing hyphen",
    "FM004": "'name' does not match the skill's parent directory name "
    "(downgraded to info under template/example-style directories)",
    "FM005": "frontmatter is missing the required 'description' key",
    "FM006": "'description' must be a non-empty plain string",
    "FM007": "unknown frontmatter key (not part of the supported schema)",
    "FM008": "nested metadata stored raw (a mapping two or more levels deep "
    "under a frontmatter key is kept as an unparsed raw string; content is "
    "not validated beyond capture)",
    "DQ001": "description too short (< 20 chars) to trigger reliably",
    "DQ002": "description contains generic filler phrasing",
    "DQ003": "description lacks trigger guidance ('use when ...')",
    "DQ004": "description exceeds the 1024-char spec limit",
    "TK001": "body exceeds 5000 estimated tokens (script-weighted heuristic: "
    "ASCII 0.25, CJK 1.0, other 0.5 tokens/char)",
    "TK002": "body exceeds 15000 estimated tokens; move detail into reference files",
    "DUP001": "skill name used by more than one SKILL.md",
    "DUP002": "descriptions near-identical across skills (SequenceMatcher >= 0.85)",
    "DUP003": "descriptions overlap heavily; triggering scope may conflict (token Jaccard >= 0.60)",
    "SEC001": "dangerous destructive shell command in body",
    "SEC002": "possible hardcoded credential/secret in body "
    "(placeholder/example/test values are downgraded to info)",
    "SEC003": "download-and-execute (pipe-to-shell / eval) pattern in body",
    "STRUCT001": "target directory contains no SKILL.md files",
    "STRUCT002": "SKILL.md file could not be read",
}

# ---------------------------------------------------------------------------
# Security patterns (body text, line-scanned)
# ---------------------------------------------------------------------------
SEC001_RE = re.compile(
    r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*[rf][a-zA-Z]*\s+/(?=\s|$|['\"`])"
    r"|\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*[rf][a-zA-Z]*\s+~(?:\s|/|$)"
    r"|\bsudo\s+rm\b"
    r"|\bmkfs(?:\.\w+)?\b"
    r"|\bdd\s+if=/dev/"
    r"|\bchmod\s+-R\s+777\s+/"
    r"|:\|:&"
    r"|\bformat\s+c:"
    r"|\bdel\s+/\b[fsq]"
    r"|\bRemove-Item\b[^;\n]*-Recurse[^;\n]*-Force\b",
    re.IGNORECASE,
)
SEC002_RE = re.compile(
    r"\bAKIA[0-9A-Z]{16}\b"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    # group(1) captures the quoted credential value for the placeholder check
    r"|\b(?:api[_-]?key|apikey|secret|password|passwd|token|access[_-]?key)\b\s*[:=]\s*[\"']([^\"'\s]{8,})[\"']"
    r"|\bghp_[A-Za-z0-9]{20,}\b"
    r"|\bxox[baprs]-[A-Za-z0-9-]{10,}\b"
    r"|\bsk-[A-Za-z0-9]{20,}\b",
    re.IGNORECASE,
)
SEC003_RE = re.compile(
    r"\bcurl\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"
    r"|\bwget\b[^|\n]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b"
    r"|\biex\s*\(\s*iwr\b"
    r"|\bInvoke-Expression\b"
    r"|\bpowershell\b[^|\n]*\s-enc(?:odedcommand)?\b"
    r"|\beval\b\s*\$\(\s*(?:curl|wget)\b",
    re.IGNORECASE,
)

_SEC_PATTERNS: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    (
        "SEC001",
        SEC001_RE,
        "dangerous destructive command",
        "Remove the destructive command or gate it behind explicit user confirmation.",
    ),
    (
        "SEC002",
        SEC002_RE,
        "possible hardcoded credential/secret",
        "Load secrets from the environment or a vault instead of embedding them.",
    ),
    (
        "SEC003",
        SEC003_RE,
        "download-and-execute pattern (pipe-to-shell / eval)",
        "Download to a file, inspect it, then run it explicitly in separate steps.",
    ),
)

_WORD_RE = re.compile(r"[a-z0-9]{3,}")


def _is_placeholder_credential(value: str) -> bool:
    """True when a SEC002 match is an obvious placeholder/example/test value.

    Documented noise policy (see the SEC002_* constants above):
    - exact placeholder values,
    - values starting with a placeholder prefix (``your-*``, ``test-*``,
      ``${...}`` template references, ...),
    - values containing ``example`` (catches ``example-*`` strings and the
      AWS documentation sample key ``AKIAIOSFODNN7EXAMPLE``) or ``xxx``,
    - angle-bracket placeholders such as ``<test-password>``.
    """
    v = value.strip().strip("'\"").lower()
    if not v:
        return False
    if v in SEC002_PLACEHOLDER_VALUES:
        return True
    if v.startswith(SEC002_PLACEHOLDER_PREFIXES):
        return True
    if "example" in v or "xxx" in v:
        return True
    if "<" in v and ">" in v:
        return True
    return False


def _fm004_severity(rel_path: str) -> str:
    """FM004 severity: info under template/example-style directories."""
    for part in rel_path.split("/")[:-1]:
        if part.lower() in FM004_TEMPLATE_DIR_MARKERS:
            return SEVERITY_INFO
    return SEVERITY_WARNING


# ---------------------------------------------------------------------------
# Per-skill checks
# ---------------------------------------------------------------------------
def check_frontmatter(doc: SkillDoc, findings: list[Finding]) -> None:
    if not doc.has_frontmatter:
        unclosed = any("never closed" in note for _, note in doc.parse_notes)
        message = (
            "frontmatter opens with '---' but is never closed"
            if unclosed
            else "no frontmatter block: SKILL.md must start with '---' on line 1"
        )
        findings.append(
            Finding(
                "FM001",
                "error",
                doc.rel_path,
                1,
                message,
                "Add a '--- ... ---' YAML frontmatter block with name and description at the top.",
            )
        )
        return
    for line_no, note in doc.parse_notes:
        findings.append(
            Finding(
                "FM001",
                "error",
                doc.rel_path,
                line_no,
                f"frontmatter line {line_no}: {note}",
                "Rewrite the line as 'key: value'; one level of nested mapping is "
                "supported (e.g. under 'metadata:'), deeper nesting is kept as a raw "
                "string (FM008); anchors and flow mappings are unsupported.",
            )
        )
    # FM008 (info): the parser accepts mappings two or more levels deep but
    # does not fully parse them -- they are stored as a raw string. That is a
    # capability limit, not an error, so it is reported at info level (never
    # gates the exit code) and never as FM001.
    for line_no, key_path in doc.raw_nested:
        findings.append(
            Finding(
                "FM008",
                "info",
                doc.rel_path,
                line_no,
                f"nested metadata '{key_path}' (depth 2+) is stored as a raw "
                "string, not fully parsed",
                None,
            )
        )

    if "name" not in doc.frontmatter:
        findings.append(
            Finding(
                "FM002",
                "error",
                doc.rel_path,
                1,
                "frontmatter is missing the required 'name' key",
                "Add 'name: <lowercase-with-hyphens>' matching the skill directory.",
            )
        )
    else:
        name_value = doc.frontmatter["name"]
        name_line = doc.key_lines.get("name", 1)
        if not isinstance(name_value, str):
            findings.append(
                Finding(
                    "FM003",
                    "error",
                    doc.rel_path,
                    name_line,
                    "'name' must be a plain scalar string",
                    "Write the name as a single-line string.",
                )
            )
        else:
            if len(name_value) > MAX_NAME_LEN or not NAME_RE.fullmatch(name_value):
                findings.append(
                    Finding(
                        "FM003",
                        "error",
                        doc.rel_path,
                        name_line,
                        f"'name' '{name_value}' is invalid: must match [a-z0-9-] (lowercase, "
                        f"hyphens allowed), max {MAX_NAME_LEN} chars, no leading/trailing hyphen",
                        "Rename the skill, e.g. 'pdf-invoice-parser'.",
                    )
                )
            if doc.dir_name and name_value != doc.dir_name:
                severity = _fm004_severity(doc.rel_path)
                suffix = (
                    " (template/example directory; downgraded to info)"
                    if severity == SEVERITY_INFO
                    else ""
                )
                findings.append(
                    Finding(
                        "FM004",
                        severity,
                        doc.rel_path,
                        name_line,
                        f"'name' '{name_value}' does not match parent directory "
                        f"'{doc.dir_name}'{suffix}",
                        "Align the directory name with the 'name' field.",
                    )
                )

    if "description" not in doc.frontmatter:
        findings.append(
            Finding(
                "FM005",
                "error",
                doc.rel_path,
                1,
                "frontmatter is missing the required 'description' key",
                "Add a 1-3 sentence 'description' saying what the skill does and when to use it.",
            )
        )
    else:
        desc_value = doc.frontmatter["description"]
        if not isinstance(desc_value, str) or not desc_value.strip():
            findings.append(
                Finding(
                    "FM006",
                    "error",
                    doc.rel_path,
                    doc.key_lines.get("description", 1),
                    "'description' must be a non-empty plain string (found empty or non-scalar value)",
                    "Write the description as a single-line string.",
                )
            )

    for key in sorted(doc.frontmatter):
        if key not in KNOWN_FRONTMATTER_KEYS:
            findings.append(
                Finding(
                    "FM007",
                    "info",
                    doc.rel_path,
                    doc.key_lines.get(key, 1),
                    f"unknown frontmatter key '{key}' "
                    f"(supported: {', '.join(sorted(KNOWN_FRONTMATTER_KEYS))})",
                    None,
                )
            )


def check_description(doc: SkillDoc, findings: list[Finding]) -> None:
    desc = doc.description
    if not isinstance(desc, str) or not desc.strip():
        return  # FM005/FM006 already reported the problem
    line = doc.key_lines.get("description", 1)
    lower = desc.lower()
    if len(desc) < MIN_DESCRIPTION_CHARS:
        findings.append(
            Finding(
                "DQ001",
                "warning",
                doc.rel_path,
                line,
                f"description is only {len(desc)} chars (< {MIN_DESCRIPTION_CHARS}); "
                "too short to disambiguate triggering",
                "State what the skill produces and when to reach for it.",
            )
        )
    if len(desc) > MAX_DESCRIPTION_CHARS:
        findings.append(
            Finding(
                "DQ004",
                "error",
                doc.rel_path,
                line,
                f"description is {len(desc)} chars (> {MAX_DESCRIPTION_CHARS} spec limit)",
                "Move detail into the skill body; keep the description to 1-3 sentences.",
            )
        )
    hits = [phrase for phrase in GENERIC_PHRASES if phrase in lower]
    if hits:
        findings.append(
            Finding(
                "DQ002",
                "warning",
                doc.rel_path,
                line,
                f"description uses generic filler phrase(s): {', '.join(hits)}",
                "Replace with concrete capabilities and inputs/outputs.",
            )
        )
    if not any(hint in lower for hint in TRIGGER_HINTS):
        findings.append(
            Finding(
                "DQ003",
                "info",
                doc.rel_path,
                line,
                "description lacks trigger guidance ('use when ...'); "
                "triggering then depends on the name alone",
                "End the description with 'Use when ...'.",
            )
        )


def check_tokens(doc: SkillDoc, findings: list[Finding]) -> None:
    tokens = doc.body_tokens
    if tokens > HARD_BODY_TOKENS:
        findings.append(
            Finding(
                "TK002",
                "error",
                doc.rel_path,
                doc.body_start_line,
                f"body is ~{tokens} estimated tokens (script-weighted estimate, "
                f"> {HARD_BODY_TOKENS} "
                "hard limit); the whole file lands in context at once",
                "Split the body: keep procedures short, move reference detail into linked files.",
            )
        )
    elif tokens > MAX_BODY_TOKENS:
        findings.append(
            Finding(
                "TK001",
                "warning",
                doc.rel_path,
                doc.body_start_line,
                f"body is ~{tokens} estimated tokens (script-weighted estimate, "
                f"> {MAX_BODY_TOKENS} "
                "recommended budget)",
                "Trim or split the body into reference files loaded on demand.",
            )
        )


def check_security(doc: SkillDoc, findings: list[Finding]) -> None:
    for offset, line_text in enumerate(doc.body.splitlines()):
        for rule_id, pattern, message, fix in _SEC_PATTERNS:
            match = pattern.search(line_text)
            if not match:
                continue
            severity = SEVERITY_WARNING
            suffix = ""
            if rule_id == "SEC002":
                # placeholder/example/test credentials are downgraded to info
                value = match.group(1) if match.group(1) is not None else match.group(0)
                if _is_placeholder_credential(value):
                    severity = SEVERITY_INFO
                    suffix = " (placeholder/example value; downgraded to info)"
            snippet = line_text.strip()[:120]
            findings.append(
                Finding(
                    rule_id,
                    severity,
                    doc.rel_path,
                    doc.body_start_line + offset,
                    f"{message}: {snippet}{suffix}",
                    fix,
                )
            )


# ---------------------------------------------------------------------------
# Cross-skill checks
# ---------------------------------------------------------------------------
def _token_jaccard(a: str, b: str) -> float:
    set_a = set(_WORD_RE.findall(a))
    set_b = set(_WORD_RE.findall(b))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def check_duplicates(docs: list[SkillDoc], findings: list[Finding]) -> None:
    by_name: dict[str, list[SkillDoc]] = {}
    for doc in docs:
        if doc.name:
            by_name.setdefault(doc.name, []).append(doc)
    for name in sorted(by_name):
        group = by_name[name]
        if len(group) > 1:
            first = group[0]
            for other in group[1:]:
                findings.append(
                    Finding(
                        "DUP001",
                        "error",
                        other.rel_path,
                        other.key_lines.get("name", 1),
                        f"skill name '{name}' is already used by {first.rel_path}",
                        "Skill names must be unique across the repository.",
                    )
                )

    described = [
        doc
        for doc in docs
        if isinstance(doc.description, str) and len(doc.description.strip()) >= 10
    ]
    for i in range(len(described)):
        for j in range(i + 1, len(described)):
            doc_a, doc_b = described[i], described[j]
            text_a = doc_a.description.lower()
            text_b = doc_b.description.lower()
            ratio = SequenceMatcher(None, text_a, text_b, autojunk=False).ratio()
            jaccard = _token_jaccard(text_a, text_b)
            if ratio >= DESC_SIMILAR_RATIO:
                findings.append(
                    Finding(
                        "DUP002",
                        "warning",
                        doc_b.rel_path,
                        doc_b.key_lines.get("description", 1),
                        f"description is near-identical to {doc_a.rel_path} "
                        f"(similarity {ratio:.2f} >= {DESC_SIMILAR_RATIO}); "
                        "one of the two may never trigger",
                        "Differentiate the descriptions or merge the skills.",
                    )
                )
            elif jaccard >= DESC_JACCARD:
                findings.append(
                    Finding(
                        "DUP003",
                        "warning",
                        doc_b.rel_path,
                        doc_b.key_lines.get("description", 1),
                        f"description overlaps heavily with {doc_a.rel_path} "
                        f"(token Jaccard {jaccard:.2f} >= {DESC_JACCARD}); "
                        "triggering scopes may conflict",
                        "Sharpen each description so the trigger scopes are disjoint.",
                    )
                )
