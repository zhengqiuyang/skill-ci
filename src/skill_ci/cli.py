"""CLI entry point.

Exit codes (documented contract):
- 0: scan completed, no error-severity findings
- 1: scan completed, at least one error-severity finding
- 2: usage or IO error (target missing/unreadable, report not writable)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import lint_path
from .render import render_json, render_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="skill-lint",
        description="Static linter for SKILL.md skill repositories (stdlib only).",
    )
    parser.add_argument("target", help="path to the skill repository root to scan")
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown", help="report format"
    )
    parser.add_argument(
        "--out", metavar="FILE", default=None, help="write the report to FILE instead of stdout"
    )
    args = parser.parse_args(argv)

    root = Path(args.target)
    if not root.is_dir():
        print(f"skill-lint: target is not a directory: {args.target}", file=sys.stderr)
        return 2

    try:
        docs, findings = lint_path(root)
    except OSError as exc:
        print(f"skill-lint: cannot scan target: {exc}", file=sys.stderr)
        return 2

    has_error = any(f.severity == "error" for f in findings)
    exit_code = 1 if has_error else 0

    if args.format == "json":
        report = render_json(str(root), docs, findings, exit_code)
    else:
        report = render_markdown(str(root), docs, findings, exit_code)

    if args.out:
        try:
            Path(args.out).write_text(report, encoding="utf-8")
        except OSError as exc:
            print(f"skill-lint: cannot write report: {exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(report)
    return exit_code
