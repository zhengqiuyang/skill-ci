"""Rule-level tests against synthetic fixtures (one fixture per rule)."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.model import SEVERITIES  # noqa: E402
from skill_ci.pipeline import lint_path  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class RuleTestBase(unittest.TestCase):
    """Copies selected synthetic fixture skills into a temp target and lints it."""

    def lint_selection(self, *names: str):
        tmp = tempfile.mkdtemp(prefix="skillci-test-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in names:
            shutil.copytree(FIXTURES / name, Path(tmp) / name)
        return lint_path(Path(tmp))

    def rules_for(self, findings, skill_dir):
        return {f.rule_id for f in findings if f.file == f"{skill_dir}/SKILL.md"}


class FrontmatterRuleTests(RuleTestBase):
    def test_good_skill_has_no_findings(self):
        _, findings = self.lint_selection("good-sample")
        self.assertEqual(findings, [])

    def test_missing_frontmatter_block(self):
        _, findings = self.lint_selection("no-frontmatter")
        self.assertEqual(self.rules_for(findings, "no-frontmatter"), {"FM001"})
        self.assertTrue(all(f.severity == "error" for f in findings))

    def test_missing_name_and_description(self):
        _, findings = self.lint_selection("missing-keys")
        self.assertEqual(self.rules_for(findings, "missing-keys"), {"FM002", "FM005"})

    def test_invalid_name_and_dir_mismatch(self):
        _, findings = self.lint_selection("bad-name")
        self.assertEqual(self.rules_for(findings, "bad-name"), {"FM003", "FM004"})

    def test_unknown_keys_are_info_with_line_numbers(self):
        _, findings = self.lint_selection("unknown-keys")
        fm007 = [f for f in findings if f.rule_id == "FM007"]
        self.assertEqual(len(fm007), 2)
        self.assertEqual(self.rules_for(findings, "unknown-keys"), {"FM007"})
        self.assertEqual([f.line for f in fm007], [4, 5])

    def test_name_dir_mismatch_only(self):
        _, findings = self.lint_selection("wrong-dir")
        self.assertEqual(self.rules_for(findings, "wrong-dir"), {"FM004"})

    def test_empty_description_is_fm006(self):
        _, findings = self.lint_selection("empty-desc")
        self.assertEqual(self.rules_for(findings, "empty-desc"), {"FM006"})


class DescriptionRuleTests(RuleTestBase):
    def test_too_short_description(self):
        _, findings = self.lint_selection("tiny-desc")
        self.assertEqual(self.rules_for(findings, "tiny-desc"), {"DQ001", "DQ003"})

    def test_generic_description(self):
        _, findings = self.lint_selection("generic-desc")
        self.assertEqual(self.rules_for(findings, "generic-desc"), {"DQ002", "DQ003"})

    def test_oversized_description_is_error(self):
        _, findings = self.lint_selection("long-desc")
        self.assertEqual(self.rules_for(findings, "long-desc"), {"DQ004"})
        self.assertTrue(any(f.severity == "error" for f in findings))
        self.assertEqual(findings[0].line, 3)


class TokenRuleTests(RuleTestBase):
    def _write_skill(self, tmp, name, body):
        skill_dir = Path(tmp) / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: Generates release notes from commits. Use when the user asks for notes.\n"
            "---\n"
            "\n" + body,
            encoding="utf-8",
        )

    def test_body_over_recommended_budget_warns(self):
        tmp = tempfile.mkdtemp(prefix="skillci-tk1-")
        self.addCleanup(shutil.rmtree, tmp, True)
        body = "# Steps\n\n" + ("x" * 20400) + "\n"  # len(body)//4 == 5102
        self._write_skill(tmp, "big-warn", body)
        _, findings = lint_path(Path(tmp))
        self.assertEqual({f.rule_id for f in findings}, {"TK001"})
        self.assertTrue(all(f.severity == "warning" for f in findings))

    def test_body_over_hard_limit_is_error(self):
        tmp = tempfile.mkdtemp(prefix="skillci-tk2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        body = "# Steps\n\n" + ("x" * 60400) + "\n"  # len(body)//4 == 15102
        self._write_skill(tmp, "big-err", body)
        _, findings = lint_path(Path(tmp))
        self.assertEqual({f.rule_id for f in findings}, {"TK002"})
        self.assertTrue(all(f.severity == "error" for f in findings))

    def test_body_within_budget_is_clean(self):
        tmp = tempfile.mkdtemp(prefix="skillci-tk3-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self._write_skill(tmp, "small", "# Steps\n\nShort body.\n")
        _, findings = lint_path(Path(tmp))
        self.assertEqual(findings, [])


class SecurityRuleTests(RuleTestBase):
    def test_dangerous_patterns_flagged_with_line_numbers(self):
        _, findings = self.lint_selection("danger-skill")
        self.assertEqual(
            {f.rule_id for f in findings}, {"SEC001", "SEC002", "SEC003"}
        )
        for finding in findings:
            self.assertEqual(finding.severity, "warning")
            self.assertGreaterEqual(finding.line, 5)  # inside the body
        by_rule = {f.rule_id: f.line for f in findings}
        self.assertEqual(by_rule["SEC001"], 8)
        self.assertEqual(by_rule["SEC003"], 13)
        self.assertEqual(by_rule["SEC002"], 19)


class DuplicateRuleTests(RuleTestBase):
    def test_duplicate_skill_name_is_error(self):
        _, findings = self.lint_selection("dup-name-a", "dup-name-b")
        dup = [f for f in findings if f.rule_id == "DUP001"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].severity, "error")
        self.assertEqual(dup[0].file, "dup-name-b/SKILL.md")
        self.assertIn("dup-name-a/SKILL.md", dup[0].message)

    def test_near_identical_descriptions(self):
        _, findings = self.lint_selection("dup-desc-a", "dup-desc-b")
        dup = [f for f in findings if f.rule_id == "DUP002"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].severity, "warning")
        self.assertIn("similarity 1.00", dup[0].message)

    def test_overlapping_descriptions_conflict_without_being_identical(self):
        _, findings = self.lint_selection("overlap-desc-a", "overlap-desc-b")
        ids = {f.rule_id for f in findings}
        self.assertIn("DUP003", ids)
        self.assertNotIn("DUP002", ids)  # ratio must stay below 0.85
        self.assertIn("Jaccard 0.73", next(f.message for f in findings if f.rule_id == "DUP003"))


class StructureTests(RuleTestBase):
    def test_empty_target_reports_struct001(self):
        tmp = tempfile.mkdtemp(prefix="skillci-empty-")
        self.addCleanup(shutil.rmtree, tmp, True)
        _, findings = lint_path(Path(tmp))
        self.assertEqual([f.rule_id for f in findings], ["STRUCT001"])
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].line, 0)

    def test_every_finding_has_rule_severity_file_and_line(self):
        all_names = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
        tmp = tempfile.mkdtemp(prefix="skillci-all-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in all_names:
            shutil.copytree(FIXTURES / name, Path(tmp) / name)
        _, findings = lint_path(Path(tmp))
        self.assertTrue(findings)
        for f in findings:
            self.assertIn(f.severity, SEVERITIES)
            self.assertTrue(f.rule_id)
            self.assertTrue(f.file)
            self.assertGreaterEqual(f.line, 0)
            self.assertTrue(f.message)

    def test_all_rule_ids_have_catalog_entry(self):
        from skill_ci.rules import RULE_CATALOG

        all_names = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
        tmp = tempfile.mkdtemp(prefix="skillci-cat-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in all_names:
            shutil.copytree(FIXTURES / name, Path(tmp) / name)
        _, findings = lint_path(Path(tmp))
        self.assertTrue({f.rule_id for f in findings} <= set(RULE_CATALOG))


if __name__ == "__main__":
    unittest.main()
