"""W2 render-shape tests: markdown grouped by rule (default) vs flat
instances (--all-instances); JSON stays instance-level (W1 contract)."""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.cli import main  # noqa: E402
from skill_ci.render import render_markdown  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

FLAT_TABLE_HEADER = "| rule_id | severity | location | message | fix hint |"


class RenderShapeTestBase(unittest.TestCase):
    def _target_with(self, *names: str) -> str:
        tmp = tempfile.mkdtemp(prefix="skillci-render-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in names:
            shutil.copytree(FIXTURES / name, Path(tmp) / name)
        return tmp

    def _run(self, target, *flags):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main([target, *flags])
        self.assertIn(code, (0, 1))
        return buf.getvalue()


class GroupedMarkdownTests(RenderShapeTestBase):
    """Default markdown groups findings by rule (W2 shape)."""

    def test_default_is_grouped_by_rule(self):
        out = self._run(self._target_with("bad-name", "tiny-desc", "good-sample"))
        self.assertIn("## Findings by rule", out)
        self.assertNotIn(FLAT_TABLE_HEADER, out)
        # one section per rule with severity + instance count
        self.assertIn("### FM003 — error, 1 instance", out)
        self.assertIn("### FM004 — warning, 1 instance", out)
        self.assertIn("### DQ001 — warning, 1 instance", out)

    def test_grouped_section_carries_meaning_fix_hint_and_locations(self):
        out = self._run(self._target_with("bad-name"))
        self.assertIn("'name' must be lowercase", out)          # catalog meaning
        self.assertIn("*Fix hint*: Rename the skill", out)      # fix hint
        self.assertIn("- `bad-name/SKILL.md:2` —", out)         # affected location

    def test_rules_sorted_ascending_and_instances_complete(self):
        out = self._run(self._target_with("bad-name", "tiny-desc", "danger-skill"))
        import re

        rules = re.findall(r"^### ([A-Z]+\d+) — ", out, flags=re.M)
        self.assertEqual(rules, sorted(rules))
        # every instance location appears exactly once in grouped lists
        for needle in ("danger-skill/SKILL.md:8", "danger-skill/SKILL.md:13", "danger-skill/SKILL.md:19"):
            self.assertEqual(out.count(needle), 1, needle)

    def test_multi_instance_rule_counts_plural(self):
        out = self._run(self._target_with("unknown-keys"))
        self.assertIn("### FM007 — info, 2 instances", out)

    def test_no_findings_grouped_message(self):
        out = self._run(self._target_with("good-sample"))
        self.assertIn("## Findings by rule", out)
        self.assertIn("No findings. All checks passed.", out)


class FlatMarkdownTests(RenderShapeTestBase):
    """--all-instances keeps the W1 per-instance table."""

    def test_flag_switches_to_flat_table(self):
        out = self._run(self._target_with("bad-name", "tiny-desc"), "--all-instances")
        self.assertIn(FLAT_TABLE_HEADER, out)
        self.assertNotIn("## Findings by rule", out)
        self.assertIn("| FM003 | error |", out)
        self.assertIn("| DQ001 | warning |", out)

    def test_flat_table_row_count_matches_findings(self):
        out = self._run(self._target_with("bad-name", "tiny-desc"), "--all-instances")
        findings_section = out.split("## Rule catalog")[0]
        rows = [
            ln
            for ln in findings_section.splitlines()
            if ln.startswith("| FM") or ln.startswith("| DQ")
        ]
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:  # every row carries one instance with all columns
            self.assertEqual(row.count(" | "), 4, row)

    def test_no_findings_flat_message(self):
        out = self._run(self._target_with("good-sample"), "--all-instances")
        self.assertIn("No findings. All checks passed.", out)


class JsonContractTests(RenderShapeTestBase):
    """JSON stays instance-level regardless of --all-instances (W1 contract)."""

    def test_json_shape_with_and_without_flag(self):
        for flags in ([], ["--all-instances"]):
            out = self._run(self._target_with("bad-name", "tiny-desc"), "--format", "json", *flags)
            payload = json.loads(out)
            ids = [f["rule_id"] for f in payload["findings"]]
            self.assertIn("FM003", ids)
            self.assertIn("DQ001", ids)
            for f in payload["findings"]:
                self.assertIn("line", f)  # instance-level: per-line detail kept

    def test_direct_render_call_defaults_to_grouped(self):
        from skill_ci.pipeline import lint_path
        from pathlib import Path as _Path

        tmp = tempfile.mkdtemp(prefix="skillci-render-direct-")
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(FIXTURES / "bad-name", _Path(tmp) / "bad-name")
        docs, findings = lint_path(_Path(tmp))
        md = render_markdown(tmp, docs, findings, 1)
        self.assertIn("## Findings by rule", md)


if __name__ == "__main__":
    unittest.main()
