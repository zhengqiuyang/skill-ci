"""W2 skill-test tests: BM25 predictor, prompts.jsonl contract, metrics.

The synthetic fixture (5 skills, 20 labeled prompts) is designed so the
metric values are known a priori:
- 12 true positives (11 clean triggers + the Chinese cn-invoice bigram path),
- exactly 1 false positive: "export the database table to a csv file"
  triggers csv-to-excel on the rare term 'csv' (df=1),
- exactly 1 false negative: the paraphrased billing prompt shares no token
  with pdf-invoice metadata,
- 6 true negatives.
=> precision == recall == 12/13. The FP/FN evidence must name the exact
offending terms (traceability contract).
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.bm25 import BM25Index, tokenize  # noqa: E402
from skill_ci.cli import main  # noqa: E402
from skill_ci.pipeline import lint_path  # noqa: E402
from skill_ci.triggers import (  # noqa: E402
    BM25_TRIGGER_THRESHOLD,
    SuiteError,
    load_suite,
    predict,
    run_suite,
    skills_from_docs,
    validate_expected,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
REPO = FIXTURES / "skilltest-repo"
SUITE = FIXTURES / "skilltest-suite" / "prompts.jsonl"

FP_PROMPT = "export the database table to a csv file"
FN_PROMPT = "read my billing document then pull out all amounts"


class SkillTestCliTests(unittest.TestCase):
    def _run(self, *args):
        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = main(["test", *args])
        return code, buf.getvalue(), err.getvalue()

    def test_fixture_metrics_are_exact(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE), "--format", "json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        metrics = payload["metrics"]
        self.assertEqual(metrics["tp"], 12)
        self.assertEqual(metrics["fp"], 1)
        self.assertEqual(metrics["fn"], 1)
        self.assertEqual(metrics["tn"], 6)
        self.assertEqual(metrics["precision"], round(12 / 13, 4))
        self.assertEqual(metrics["recall"], round(12 / 13, 4))

    def test_false_positive_is_traceable_to_the_offending_term(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE), "--format", "json")
        payload = json.loads(out)
        fps = payload["false_positives"]
        self.assertEqual(len(fps), 1)
        fp = fps[0]
        self.assertEqual(fp["prompt"], FP_PROMPT)
        self.assertIsNone(fp["expected"])
        self.assertEqual(fp["predicted"], "csv-to-excel")
        terms = [t for t, _ in fp["evidence_terms"]]
        self.assertIn("csv", terms)  # the word in the description that caused it
        top = max(fp["evidence_terms"], key=lambda pair: pair[1])
        self.assertEqual(top[0], "csv")

    def test_false_negative_names_expected_and_reason(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE), "--format", "json")
        payload = json.loads(out)
        fns = payload["false_negatives"]
        self.assertEqual(len(fns), 1)
        fn = fns[0]
        self.assertEqual(fn["prompt"], FN_PROMPT)
        self.assertEqual(fn["expected"], "pdf-invoice")
        self.assertIsNone(fn["predicted"])
        self.assertEqual(fn["evidence_terms"], [])  # zero term overlap

    def test_per_skill_distribution_counts(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE), "--format", "json")
        payload = json.loads(out)
        dist = {row["skill_id"]: row for row in payload["per_skill"]}
        self.assertEqual(dist["csv-to-excel"]["predicted_hits"], 4)  # 3 TP + 1 FP
        self.assertEqual(dist["csv-to-excel"]["expected_hits"], 3)
        self.assertEqual(dist["pdf-invoice"]["expected_hits"], 4)
        self.assertEqual(dist["pdf-invoice"]["predicted_hits"], 3)
        self.assertEqual(dist["cn-invoice"]["predicted_hits"], 2)
        self.assertEqual(dist["(none)"]["expected_hits"], 7)
        self.assertEqual(dist["(none)"]["predicted_hits"], 7)

    def test_token_cost_uses_cjk_weighted_estimator(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE), "--format", "json")
        payload = json.loads(out)
        cost = payload["token_cost"]
        per_skill = {r["skill_id"]: r for r in cost["per_skill"]}
        self.assertEqual(
            cost["suite_total_tokens"],
            sum(r["total_tokens"] for r in cost["per_skill"]),
        )
        # Chinese description: ~1 token/char, far above the len//4 baseline
        cn = per_skill["cn-invoice"]
        raw = (REPO / "cn-invoice" / "SKILL.md").read_text(encoding="utf-8")
        desc = raw.split("description: ", 1)[1].splitlines()[0]
        self.assertGreater(cn["description_tokens"], len(desc) // 4 * 2)
        self.assertGreaterEqual(cn["description_tokens"], len(desc) - 3)

    def test_markdown_report_contains_metrics_and_evidence(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE))
        self.assertEqual(code, 0)
        self.assertIn("# skill-test report", out)
        self.assertIn("Trigger precision: 0.9231", out)
        self.assertIn("Trigger recall: 0.9231", out)
        self.assertIn(FP_PROMPT, out)
        self.assertIn(FN_PROMPT, out)
        self.assertIn("'csv' (", out)  # evidence term with contribution
        self.assertIn("Per-skill hit distribution", out)
        self.assertIn("Token cost of trigger metadata", out)
        self.assertIn("**186**", out)  # suite total from the pinned fixture

    def test_chinese_prompt_triggers_chinese_skill(self):
        code, out, _ = self._run(str(REPO), "--suite", str(SUITE), "--format", "json")
        payload = json.loads(out)
        cn = [
            p
            for p in payload["predictions"]
            if p["expected"] == "cn-invoice" and p["predicted"] == "cn-invoice"
        ]
        self.assertEqual(len(cn), 2)
        cn_prompts = [p["prompt"] for p in cn]
        self.assertTrue(any("中文发票" in prompt for prompt in cn_prompts))

    # --- usage errors (exit 2) -------------------------------------------
    def test_empty_suite_is_usage_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-empty-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = tmp / "prompts.jsonl"
        suite.write_text("\n\n", encoding="utf-8")
        code, _, err = self._run(str(REPO), "--suite", str(suite))
        self.assertEqual(code, 2)
        self.assertIn("no prompt entries", err)

    def test_all_negative_suite_precision_recall_one(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-neg-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = tmp / "prompts.jsonl"
        suite.write_text(
            '{"prompt": "What\'s the weather like today?", "expected": null}\n'
            '{"prompt": "Tell me a joke about programmers", "expected": "none"}\n'
            '{"prompt": "Help me plan my vacation itinerary", "expected": null}\n',
            encoding="utf-8",
        )
        code, out, _ = self._run(str(REPO), "--suite", str(suite), "--format", "json")
        self.assertEqual(code, 0)
        metrics = json.loads(out)["metrics"]
        self.assertEqual(metrics["tp"], 0)
        self.assertEqual(metrics["tn"], 3)
        self.assertEqual(metrics["precision"], 1.0)  # documented empty-denominator rule
        self.assertEqual(metrics["recall"], 1.0)

    def test_unknown_expected_skill_id_is_usage_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-bad-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = tmp / "prompts.jsonl"
        suite.write_text(
            '{"prompt": "convert csv", "expected": "no-such-skill"}\n', encoding="utf-8"
        )
        code, _, err = self._run(str(REPO), "--suite", str(suite))
        self.assertEqual(code, 2)
        self.assertIn("unknown skill id", err)
        self.assertIn("no-such-skill", err)

    def test_malformed_suite_line_reports_line_number(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-mal-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = tmp / "prompts.jsonl"
        suite.write_text('{"prompt": "ok", "expected": null}\nnot json at all\n', encoding="utf-8")
        code, _, err = self._run(str(REPO), "--suite", str(suite))
        self.assertEqual(code, 2)
        self.assertIn("line 2", err)

    def test_suite_entry_missing_expected_key_is_usage_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-key-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = tmp / "prompts.jsonl"
        suite.write_text('{"prompt": "only prompt"}\n', encoding="utf-8")
        code, _, err = self._run(str(REPO), "--suite", str(suite))
        self.assertEqual(code, 2)
        self.assertIn("line 1", err)

    def test_missing_suite_file_is_usage_error(self):
        code, _, err = self._run(str(REPO), "--suite", "Z:/__no_suite__.jsonl")
        self.assertEqual(code, 2)
        self.assertIn("cannot read suite file", err)

    def test_repo_without_skills_is_usage_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-repo-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        code, _, err = self._run(str(tmp), "--suite", str(SUITE))
        self.assertEqual(code, 2)
        self.assertIn("no indexable skills", err)

    def test_missing_target_is_usage_error(self):
        code, _, err = self._run("Z:/__no_repo__/", "--suite", str(SUITE))
        self.assertEqual(code, 2)

    def test_out_writes_report_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="skillci-suite-out-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        report = tmp / "report.md"
        code, _, _ = self._run(str(REPO), "--suite", str(SUITE), "--out", str(report))
        self.assertEqual(code, 0)
        text = report.read_text(encoding="utf-8")
        self.assertIn("# skill-test report", text)


class BM25UnitTests(unittest.TestCase):
    def test_tokenize_words_and_cjk_bigrams(self):
        self.assertEqual(tokenize("CSV-to-Excel!"), ["csv", "to", "excel"])
        tokens = tokenize("解析中文发票")
        self.assertEqual(tokens, ["解析", "析中", "中文", "文发", "发票"])
        self.assertEqual(tokenize("票"), ["票"])  # single-char run stays single

    def test_idf_prefers_rare_terms(self):
        index = BM25Index({
            "a": tokenize("alpha beta"),
            "b": tokenize("alpha gamma"),
            "c": tokenize("alpha delta"),
        })
        self.assertGreater(index.idf("beta"), index.idf("alpha"))

    def test_search_no_overlap_scores_zero(self):
        index = BM25Index({"a": tokenize("alpha beta")})
        self.assertEqual(index.search(tokenize("omega")), {})

    def test_explain_contributions_sum_to_score(self):
        docs = {"a": tokenize("convert csv exports into workbooks"),
                "b": tokenize("parse pdf invoices")}
        index = BM25Index(docs)
        query = tokenize("convert csv")
        scores = index.search(query)
        total = sum(w for _, w in index.explain(query, "a"))
        self.assertAlmostEqual(scores["a"], total, places=3)
        self.assertEqual(index.explain(query, "b"), [])


class PredictorBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        docs, _ = lint_path(REPO)
        cls.entries = skills_from_docs(docs)
        from skill_ci.bm25 import BM25Index as _Idx

        cls.index = _Idx({e.skill_id: tokenize(e.text) for e in cls.entries})

    def test_predict_returns_highest_scoring_skill_above_threshold(self):
        prediction = predict("convert this csv into a workbook", self.entries, self.index)
        self.assertEqual(prediction.predicted, "csv-to-excel")
        self.assertGreaterEqual(prediction.scores[0][1], BM25_TRIGGER_THRESHOLD)

    def test_predict_none_when_nothing_scores(self):
        prediction = predict("zzz qqq unknown gibberish", self.entries, self.index)
        self.assertIsNone(prediction.predicted)
        self.assertEqual(prediction.scores, [])

    def test_fallback_fires_when_bm25_below_artificial_threshold(self):
        """With an impossible threshold, the substring fallback still routes
        a verbatim-description prompt to its skill."""
        prediction = predict(
            "use when the user prepares a release",
            self.entries,
            self.index,
            threshold=1e9,
        )
        self.assertEqual(prediction.predicted, "changelog-writer")
        self.assertTrue(prediction.via_fallback)

    def test_validate_expected_accepts_none_and_known_ids(self):
        validate_expected([("p1", None), ("p2", "csv-to-excel")], ["csv-to-excel"])
        with self.assertRaises(SuiteError):
            validate_expected([("p1", "ghost-skill")], ["csv-to-excel"])

    def test_contract_documented_in_module_docstring(self):
        import skill_ci.triggers as triggers_module

        self.assertIn("prompts.jsonl", triggers_module.__doc__)
        self.assertIn("expected", triggers_module.__doc__)


class SkillTestLauncherTests(unittest.TestCase):
    """bin/skill-test real-run coverage (same launcher semantics as skill-lint)."""

    def _write_suite(self, tmp: Path) -> Path:
        suite = tmp / "prompts.jsonl"
        shutil.copy(SUITE, suite)
        return suite

    def test_sh_launcher_runs_skilltest(self):
        bash = shutil.which("bash")
        if bash is None:
            self.skipTest("bash not available")
        tmp = Path(tempfile.mkdtemp(prefix="skillci-test-launcher-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = self._write_suite(tmp)
        proc = subprocess.run(
            [bash, str(REPO_ROOT / "bin" / "skill-test"), str(REPO), "--suite", str(suite)],
            cwd=str(tmp.parent),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Trigger precision", proc.stdout)

    def test_cmd_launcher_runs_skilltest(self):
        if os.name != "nt":
            self.skipTest("cmd.exe launcher is Windows-only")
        tmp = Path(tempfile.mkdtemp(prefix="skillci-test-launcher-cmd-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        suite = self._write_suite(tmp)
        quoted = " ".join(f'"{a}"' if " " in a else a for a in
                          [str(REPO), "--suite", str(suite)])
        proc = subprocess.run(
            f'"{REPO_ROOT / "bin" / "skill-test.cmd"}" {quoted}',
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Trigger precision", proc.stdout)


if __name__ == "__main__":
    unittest.main()
