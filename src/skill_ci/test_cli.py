"""``python -m skill_ci test`` entry point (skill-test, W2).

Usage::

    python -m skill_ci test <repo> --suite prompts.jsonl
                            [--format markdown|json] [--out FILE]
                            [--threshold FLOAT]

- <repo>: directory containing skills as <skill-name>/SKILL.md (same layout
  skill-lint scans).
- --suite: labeled prompts.jsonl file (contract documented in
  skill_ci.triggers and README.md).
- Exit codes: 0 = suite ran (regardless of metric values; skill-test is a
  measurement tool, not a pass/fail gate), 2 = usage/IO error (missing
  repo/suite, malformed suite line, unknown expected skill id).

The same CLI is available as ``bin/skill-test`` / ``bin/skill-test.cmd``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import lint_path
from .triggers import (
    BM25_TRIGGER_THRESHOLD,
    SuiteError,
    load_suite,
    per_skill_distribution,
    run_suite,
    skills_from_docs,
    token_cost,
    validate_expected,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-test",
        description="Evaluate skill triggering against a labeled prompt suite "
        "(deterministic BM25 + fallback; no LLM, no network).",
    )
    parser.add_argument("target", help="skill repository root to index")
    parser.add_argument(
        "--suite", metavar="FILE", required=True, help="labeled prompts.jsonl file"
    )
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown", help="report format"
    )
    parser.add_argument(
        "--out", metavar="FILE", default=None, help="write the report to FILE instead of stdout"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=BM25_TRIGGER_THRESHOLD,
        help=f"BM25 score threshold for a trigger (default {BM25_TRIGGER_THRESHOLD})",
    )
    args = parser.parse_args(argv)

    root = Path(args.target)
    if not root.is_dir():
        print(f"skill-test: target is not a directory: {args.target}", file=sys.stderr)
        return 2

    try:
        docs, findings = lint_path(root)
    except OSError as exc:
        print(f"skill-test: cannot scan target: {exc}", file=sys.stderr)
        return 2
    skill_entries = skills_from_docs(docs)
    if not skill_entries:
        print(
            "skill-test: no indexable skills under target (skills need a valid 'name' "
            "in frontmatter)",
            file=sys.stderr,
        )
        return 2

    try:
        suite_path = Path(args.suite)
        entries = load_suite(suite_path)
        validate_expected(entries, [e.skill_id for e in skill_entries])
    except SuiteError as exc:
        print(f"skill-test: {exc}", file=sys.stderr)
        return 2

    report = run_suite(entries, skill_entries, threshold=args.threshold)
    distribution = per_skill_distribution(entries, report.predictions)
    cost = token_cost(skill_entries)

    if args.format == "json":
        payload = {
            "target": str(root),
            "suite": args.suite,
            "threshold": args.threshold,
            "skills_indexed": len(skill_entries),
            "prompts": len(entries),
            "metrics": {
                "precision": round(report.precision, 4),
                "recall": round(report.recall, 4),
                "tp": report.tp,
                "tn": report.tn,
                "fp": len(report.false_positives),
                "fn": len(report.false_negatives),
            },
            "false_positives": [_pred_row(p) for p in report.false_positives],
            "false_negatives": [_pred_row(p) for p in report.false_negatives],
            "per_skill": distribution,
            "token_cost": cost,
            "predictions": [_pred_row(p) for p in report.predictions],
        }
        rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    else:
        rendered = render_markdown(root, args.suite, args.threshold, len(entries),
                                   len(skill_entries), report, distribution, cost)

    if args.out:
        try:
            Path(args.out).write_text(rendered, encoding="utf-8")
        except OSError as exc:
            print(f"skill-test: cannot write report: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)
    return 0


def _pred_row(p) -> dict[str, object]:
    return {
        "prompt": p.prompt,
        "expected": p.expected,
        "predicted": p.predicted,
        "via_fallback": p.via_fallback,
        "top_scores": p.scores,
        "evidence_terms": p.evidence,
    }


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_markdown(root, suite_path, threshold, n_prompts, n_skills, report,
                    distribution, cost) -> str:
    lines: list[str] = []
    lines.append("# skill-test report")
    lines.append("")
    lines.append(f"- Target: `{root}`")
    lines.append(f"- Suite: `{suite_path}` ({n_prompts} prompts)")
    lines.append(f"- Skills indexed: {n_skills}")
    lines.append(f"- Trigger threshold (BM25): {threshold} (+ substring fallback)")
    lines.append(
        f"- Trigger precision: {report.precision:.4f} "
        f"(TP {report.tp} / predicted positives {report.tp + len(report.false_positives)})"
    )
    lines.append(
        f"- Trigger recall: {report.recall:.4f} "
        f"(TP {report.tp} / labeled positives {report.tp + len(report.false_negatives)})"
    )
    lines.append(
        f"- Confusion: TP {report.tp}, FP {len(report.false_positives)}, "
        f"FN {len(report.false_negatives)}, TN {report.tn}"
    )
    lines.append("")

    lines.append("## False positives (a skill fired that should not have)")
    lines.append("")
    if report.false_positives:
        for p in report.false_positives:
            lines.append(
                f"- prompt {_quote(p.prompt)} -> predicted `{p.predicted}` "
                f"(expected: {p.expected or 'none'})"
            )
            lines.append(f"  - evidence: {evidence_text(p)}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append("## False negatives (a labeled skill was missed or wrong)")
    lines.append("")
    if report.false_negatives:
        for p in report.false_negatives:
            if p.predicted is None:
                best = p.scores[0] if p.scores else None
                why = (
                    f"best candidate `{best[0]}` scored {best[1]} < threshold"
                    if best
                    else "no term overlap at all"
                )
                lines.append(
                    f"- prompt {_quote(p.prompt)} -> predicted none "
                    f"(expected: `{p.expected}`); {why}"
                )
            else:
                lines.append(
                    f"- prompt {_quote(p.prompt)} -> predicted `{p.predicted}` "
                    f"instead of `{p.expected}`"
                )
            lines.append(f"  - evidence: {evidence_text(p)}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append("## Per-skill hit distribution")
    lines.append("")
    lines.append("| skill | expected hits | predicted hits |")
    lines.append("| --- | ---: | ---: |")
    for row in distribution:
        lines.append(
            f"| {row['skill_id']} | {row['expected_hits']} | {row['predicted_hits']} |"
        )
    lines.append("")

    lines.append("## Token cost of trigger metadata (script-weighted estimate)")
    lines.append("")
    lines.append("| skill | name | description | when_to_use | total |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in cost["per_skill"]:
        lines.append(
            f"| {row['skill_id']} | {row['name_tokens']} | {row['description_tokens']} "
            f"| {row['when_to_use_tokens']} | {row['total_tokens']} |"
        )
    lines.append(f"| **suite total** |  |  |  | **{cost['suite_total_tokens']}** |")
    lines.append("")
    lines.append(
        "Whole-suite context load if every skill's trigger metadata is "
        f"loaded at once: ~{cost['suite_total_tokens']} tokens."
    )
    lines.append("")
    lines.append(
        "Traceability: every FP/FN above lists the query terms that produced "
        "its score and each term's BM25 contribution (idf x tf-weight), so each "
        "error is explainable down to the words in the offending description."
    )
    lines.append("")
    return "\n".join(lines)


def evidence_text(p) -> str:
    if p.via_fallback:
        return "matched via document-substring fallback rule"
    if p.evidence:
        return ", ".join(f"'{term}' ({w})" for term, w in p.evidence)
    return "no matching terms"
