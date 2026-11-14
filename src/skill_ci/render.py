"""JSON and Markdown rendering. Both render from the same findings list."""

from __future__ import annotations

import json

from .model import Finding, SkillDoc
from .rules import RULE_CATALOG


def summarize(findings: list[Finding]) -> dict[str, int]:
    return {
        "errors": sum(1 for f in findings if f.severity == "error"),
        "warnings": sum(1 for f in findings if f.severity == "warning"),
        "infos": sum(1 for f in findings if f.severity == "info"),
    }


def _skill_row(doc: SkillDoc) -> dict[str, object]:
    desc = doc.description
    return {
        "path": doc.rel_path,
        "name": doc.name,
        "body_tokens": doc.body_tokens,
        "description_chars": len(desc) if isinstance(desc, str) else 0,
    }


def render_json(target: str, docs: list[SkillDoc], findings: list[Finding], exit_code: int) -> str:
    payload = {
        "target": target,
        "skills_scanned": len(docs),
        "skills": [_skill_row(d) for d in sorted(docs, key=lambda d: d.rel_path)],
        "summary": {**summarize(findings), "exit_code": exit_code},
        "findings": [f.to_dict() for f in findings],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(
    target: str, docs: list[SkillDoc], findings: list[Finding], exit_code: int
) -> str:
    counts = summarize(findings)
    lines: list[str] = []
    lines.append("# skill-lint report")
    lines.append("")
    lines.append(f"- Target: `{target}`")
    lines.append(f"- Skills scanned: {len(docs)}")
    lines.append(
        f"- Findings: {counts['errors']} error(s), {counts['warnings']} warning(s), "
        f"{counts['infos']} info"
    )
    lines.append(
        "- Exit code: "
        f"{exit_code} (0 = no error findings, 1 = error findings present, 2 = usage/IO error)"
    )
    lines.append("")
    if docs:
        lines.append("## Skill inventory")
        lines.append("")
        lines.append("| skill | name | body tokens (est.) | description chars |")
        lines.append("| --- | --- | ---: | ---: |")
        for doc in sorted(docs, key=lambda d: d.rel_path):
            desc = doc.description
            desc_chars = len(desc) if isinstance(desc, str) else 0
            lines.append(
                f"| `{_md_cell(doc.rel_path)}` | {_md_cell(doc.name or '-')} "
                f"| {doc.body_tokens} | {desc_chars} |"
            )
        lines.append("")
    lines.append("## Findings")
    lines.append("")
    if findings:
        lines.append("| rule_id | severity | location | message | fix hint |")
        lines.append("| --- | --- | --- | --- | --- |")
        for f in findings:
            location = f"`{_md_cell(f.file)}`" if f.line == 0 else f"`{_md_cell(f.file)}:{f.line}`"
            lines.append(
                f"| {f.rule_id} | {f.severity} | {location} | {_md_cell(f.message)} "
                f"| {_md_cell(f.fix_hint or '-')} |"
            )
    else:
        lines.append("No findings. All checks passed.")
    lines.append("")
    lines.append("## Rule catalog")
    lines.append("")
    lines.append("| rule_id | meaning |")
    lines.append("| --- | --- |")
    for rule_id in sorted(RULE_CATALOG):
        lines.append(f"| {rule_id} | {_md_cell(RULE_CATALOG[rule_id])} |")
    lines.append("")
    return "\n".join(lines)
