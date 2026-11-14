"""Rule-level tests against synthetic fixtures (one fixture per rule)."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.frontmatter import parse_skill_text  # noqa: E402
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


class W3RegressionNetTests(RuleTestBase):
    """W3.0 regression net: pins that must hold both before and after the
    parser learns one-level nested metadata mappings."""

    def test_empty_metadata_with_stray_line_is_fm001(self):
        _, findings = self.lint_selection("empty-metadata-bad")
        self.assertEqual(self.rules_for(findings, "empty-metadata-bad"), {"FM001"})
        self.assertEqual([f.line for f in findings], [5])
        self.assertTrue(all(f.severity == "error" for f in findings))

    def test_empty_quoted_description_is_fm006(self):
        _, findings = self.lint_selection("quoted-desc-empty")
        self.assertEqual(self.rules_for(findings, "quoted-desc-empty"), {"FM006"})
        self.assertEqual([f.line for f in findings], [3])

    def test_name_dir_mismatch_outside_template_dirs_keeps_warning(self):
        _, findings = self.lint_selection("wrong-dir")
        fm004 = [f for f in findings if f.rule_id == "FM004"]
        self.assertEqual([f.severity for f in fm004], ["warning"])

    def test_non_placeholder_secret_keeps_warning(self):
        tmp = tempfile.mkdtemp(prefix="skillci-sec2net-")
        self.addCleanup(shutil.rmtree, tmp, True)
        skill_dir = Path(tmp) / "sec-real"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: sec-real\n"
            "description: Rotates database credentials. Use when a secret leaks.\n"
            "---\n"
            'password = "S3cur3-P@ss-2024!"\n',
            encoding="utf-8",
        )
        _, findings = lint_path(Path(tmp))
        sec002 = [f for f in findings if f.rule_id == "SEC002"]
        self.assertEqual([f.severity for f in sec002], ["warning"])


class NestedMetadataRuleTests(RuleTestBase):
    """W3.0: unknown keys under ``metadata:`` are allowed (no FM001/FM007);
    top-level unknown keys stay FM007 even with a nested-map value."""

    def test_nested_metadata_subkeys_are_allowed(self):
        _, findings = self.lint_selection("nested-metadata")
        self.assertEqual(findings, [])

    def test_stray_line_inside_nested_map_is_fm001(self):
        _, findings = self.lint_selection("nested-metadata-bad")
        self.assertEqual(self.rules_for(findings, "nested-metadata-bad"), {"FM001"})
        self.assertEqual([f.line for f in findings], [6])

    def test_quoted_metadata_lints_clean(self):
        _, findings = self.lint_selection("quoted-metadata")
        self.assertEqual(findings, [])

    def test_nested_list_values_lint_clean(self):
        _, findings = self.lint_selection("list-metadata")
        self.assertEqual(findings, [])

    def test_stray_line_inside_nested_list_is_fm001(self):
        _, findings = self.lint_selection("list-metadata-bad")
        self.assertEqual(self.rules_for(findings, "list-metadata-bad"), {"FM001"})
        self.assertEqual([f.line for f in findings], [7])

    def test_empty_metadata_lints_clean(self):
        _, findings = self.lint_selection("empty-metadata")
        self.assertEqual(findings, [])

    def test_nested_map_under_unknown_top_level_key_is_fm007_only(self):
        _, findings = self.lint_selection("unknown-nested")
        self.assertEqual(self.rules_for(findings, "unknown-nested"), {"FM007"})
        self.assertEqual([f.severity for f in findings], ["info"])
        self.assertEqual([f.line for f in findings], [4])

    def test_slash_in_nested_key_lints_clean(self):
        _, findings = self.lint_selection("nested-slash-key")
        self.assertEqual(findings, [])

    def test_nested_block_scalar_lints_clean(self):
        _, findings = self.lint_selection("nested-block-scalar")
        self.assertEqual(findings, [])

    def test_slash_in_nested_key_value(self):
        doc = parse_skill_text(
            "---\n"
            "name: nested-slash-key\n"
            "description: Use when testing a namespaced metadata key.\n"
            "metadata:\n"
            "  opencode/autoinvoke: false\n"
            "---\n"
        )
        self.assertEqual(
            doc.frontmatter["metadata"]["opencode/autoinvoke"], "false"
        )
        self.assertEqual(doc.raw_nested, [])

    def test_nested_block_scalar_values(self):
        doc = parse_skill_text(
            "---\n"
            "name: nested-block-scalar\n"
            "description: Use when testing nested block scalar values.\n"
            "metadata:\n"
            "  folded: >-\n"
            "    a\n"
            "    b\n"
            "  literal: |-\n"
            "    c\n"
            "    d\n"
            "---\n"
        )
        self.assertEqual(doc.frontmatter["metadata"]["folded"], "a b")
        self.assertEqual(doc.frontmatter["metadata"]["literal"], "c\nd")
        self.assertEqual(doc.raw_nested, [])


class W3NoiseReductionTests(RuleTestBase):
    """W3.0 noise policy: SEC002 placeholder/example/test credentials and
    FM004 mismatches under template/example-style directories are info."""

    def _write_body_skill(self, tmp, name, body):
        skill_dir = Path(tmp) / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: Handles credentials. Use when secrets are configured.\n"
            "---\n"
            + body,
            encoding="utf-8",
        )

    def test_placeholder_passwords_downgraded_to_info(self):
        tmp = tempfile.mkdtemp(prefix="skillci-sec2ph-")
        self.addCleanup(shutil.rmtree, tmp, True)
        bodies = [
            'self.user = User.objects.create_user("alice", password="<test-password>")\n',
            'password: "your-password-here"\n',
            'api_key = "example-key-123456"\n',
            'token = "xxxxxxxxxx"\n',
            'secret = "test-secret-value"\n',
            'password = "${DB_PASSWORD}"\n',
        ]
        for i, body in enumerate(bodies):
            self._write_body_skill(tmp, f"sec-placeholder-{i}", body)
        _, findings = lint_path(Path(tmp))
        sec002 = [f for f in findings if f.rule_id == "SEC002"]
        self.assertEqual(len(sec002), len(bodies))
        self.assertTrue(all(f.severity == "info" for f in sec002))
        self.assertTrue(all("downgraded to info" in f.message for f in sec002))
        # info findings never trip the error-gated exit code
        self.assertFalse(any(f.severity == "error" for f in findings))

    def test_aws_documentation_example_key_downgraded_to_info(self):
        tmp = tempfile.mkdtemp(prefix="skillci-sec2aws-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self._write_body_skill(tmp, "sec-aws-doc", "aws_access_key_id = AKIAIOSFODNN7EXAMPLE\n")
        _, findings = lint_path(Path(tmp))
        sec002 = [f for f in findings if f.rule_id == "SEC002"]
        self.assertEqual([f.severity for f in sec002], ["info"])

    def test_real_secret_stays_warning(self):
        tmp = tempfile.mkdtemp(prefix="skillci-sec2real-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self._write_body_skill(tmp, "sec-real", 'api_key = "sk-live-0123456789abcdef"\n')
        _, findings = lint_path(Path(tmp))
        sec002 = [f for f in findings if f.rule_id == "SEC002"]
        self.assertEqual([f.severity for f in sec002], ["warning"])

    def test_template_directory_mismatch_downgraded_to_info(self):
        _, findings = self.lint_selection("template")
        fm004 = [f for f in findings if f.rule_id == "FM004"]
        self.assertEqual(len(fm004), 1)
        self.assertEqual(fm004[0].severity, "info")
        self.assertIn("template/example directory", fm004[0].message)

    def test_noise_policy_is_configured_constants(self):
        from skill_ci import rules

        # documented, configurable constants -- not hardcoded repo names
        self.assertIn("your-", rules.SEC002_PLACEHOLDER_PREFIXES)
        self.assertIn("test-", rules.SEC002_PLACEHOLDER_PREFIXES)
        self.assertIn("<placeholder>", rules.SEC002_PLACEHOLDER_VALUES)
        for marker in ("template", "templates", "example", "examples"):
            self.assertIn(marker, rules.FM004_TEMPLATE_DIR_MARKERS)
        self.assertTrue(all(m.islower() for m in rules.FM004_TEMPLATE_DIR_MARKERS))


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


class FrontmatterWhitelistTests(RuleTestBase):
    """W3.1: Claude Code frontmatter extension keys（2026-11 实测于公开 skill
    仓库）are accepted -- no FM007 for any of them."""

    EXT_FIXTURES = (
        "ext-effort",
        "ext-compatibility",
        "ext-context",
        "ext-argument-hint",
        "ext-user-invocable",
        "ext-disable-model-invocation",
    )

    def test_extension_keys_lint_clean(self):
        for name in self.EXT_FIXTURES:
            with self.subTest(fixture=name):
                _, findings = self.lint_selection(name)
                self.assertEqual(findings, [])

    def test_whitelist_contains_extension_keys(self):
        from skill_ci import rules

        for key in (
            "effort",
            "compatibility",
            "context",
            "argument-hint",
            "user-invocable",
            "disable-model-invocation",
        ):
            self.assertIn(key, rules.KNOWN_FRONTMATTER_KEYS)
            self.assertIn(key, rules.CLAUDE_CODE_EXTENSION_KEYS)

    def test_truly_unknown_key_still_fm007(self):
        _, findings = self.lint_selection("unknown-keys")
        self.assertEqual(self.rules_for(findings, "unknown-keys"), {"FM007"})


class NestedMetadataDeepTests(RuleTestBase):
    """W3.1: depth-2+ nested mappings under ``metadata:`` must not be FM001;
    the capability limit is reported as FM008 (info) instead."""

    def test_two_level_nesting_is_fm008_not_fm001(self):
        _, findings = self.lint_selection("nested-metadata-deep")
        self.assertEqual(self.rules_for(findings, "nested-metadata-deep"), {"FM008"})
        self.assertTrue(all(f.severity == "info" for f in findings))
        self.assertEqual([f.line for f in findings], [5])
        self.assertIn("raw string", findings[0].message)

    def test_two_level_nesting_bad_sibling_line_stays_fm001(self):
        _, findings = self.lint_selection("nested-metadata-deep-bad")
        self.assertEqual(
            self.rules_for(findings, "nested-metadata-deep-bad"), {"FM001", "FM008"}
        )
        fm001 = [f for f in findings if f.rule_id == "FM001"]
        self.assertEqual([f.severity for f in fm001], ["error"])
        self.assertEqual([f.line for f in fm001], [7])

    def test_fm008_has_catalog_entry(self):
        from skill_ci.rules import RULE_CATALOG

        self.assertIn("FM008", RULE_CATALOG)
        self.assertIn("raw", RULE_CATALOG["FM008"])

    def test_fm008_never_gates_exit_code(self):
        # info findings alone must keep the CLI exit code at 0
        _, findings = self.lint_selection("nested-metadata-deep")
        self.assertTrue(findings)
        self.assertFalse(any(f.severity == "error" for f in findings))


if __name__ == "__main__":
    unittest.main()
