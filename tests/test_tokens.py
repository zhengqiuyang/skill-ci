"""W2 token estimator tests: script-weighted calibration + CJK fixture.

Calibration contract (documented in skill_ci/tokens.py):
the estimator is calibrated against the *documented reference weights*
(ASCII 0.25, CJK 1.0, other 0.5 tokens/char). Every mixed-content sample
must agree with an independently recomputed weighted reference within 20%
(self-consistency calibration; real tokenizer validation is W3 scope).
"""

import shutil
import sys
import tempfile
import unittest
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.model import SkillDoc  # noqa: E402
from skill_ci.pipeline import lint_path  # noqa: E402
from skill_ci.tokens import (  # noqa: E402
    CJK_TOKENS_PER_CHAR,
    OTHER_TOKENS_PER_CHAR,
    ASCII_TOKENS_PER_CHAR,
    estimate_tokens,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"

# Test-side independent tier classifier (regex, deliberately not the
# implementation's loop) used to recompute the reference values.
_CJK_RE = re.compile(
    "[\u3000-\u303f\u3040-\u30ff\u3130-\u318f\u3400-\u4dbf\u4e00-\u9fff"
    "\uac00-\ud7af\uf900-\ufaff\uff00-\uffef\U00020000-\U000323af]"
)


def _reference_tokens(text: str) -> float:
    """Independent reference: documented weights applied to test-side counts."""
    n_cjk = len(_CJK_RE.findall(text))
    n_ascii = sum(1 for ch in text if ord(ch) < 0x80)
    n_other = len(text) - n_cjk - n_ascii
    return (
        ASCII_TOKENS_PER_CHAR * n_ascii
        + CJK_TOKENS_PER_CHAR * n_cjk
        + OTHER_TOKENS_PER_CHAR * n_other
    )


class EstimatorUnitTests(unittest.TestCase):
    def test_pure_ascii_is_exactly_len_quarter(self):
        for text in ("", "abcd", "hello world!\n", "x" * 20410, "y" * 60410):
            self.assertEqual(estimate_tokens(text), len(text) // 4, repr(text[:40]))

    def test_pure_cjk_is_one_token_per_char(self):
        self.assertEqual(estimate_tokens("中文测试"), 4)
        self.assertEqual(estimate_tokens("简体中文的技能描述"), 9)

    def test_kana_and_hangul_use_cjk_weight(self):
        self.assertEqual(estimate_tokens("カタカナ"), 4)      # katakana
        self.assertEqual(estimate_tokens("한국어문장"), 5)     # hangul syllables

    def test_other_tier_is_half_weight(self):
        self.assertEqual(estimate_tokens("тест"), 2)          # 4 cyrillic chars
        self.assertEqual(estimate_tokens("Привет мир"), 4)    # 9 cyrillic + 1 ascii space = int(4.75)
        self.assertEqual(estimate_tokens("Σφαλμάτων"), 4)     # 9 greek chars = int(4.5)

    def test_empty_string_is_zero(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_weights_are_exact_powers_of_two(self):
        # Guarantees the weighted sum is float-exact: no rounding fuzz.
        for w in (ASCII_TOKENS_PER_CHAR, CJK_TOKENS_PER_CHAR, OTHER_TOKENS_PER_CHAR):
            self.assertIn(w, (0.25, 1.0, 0.5))


class CalibrationTests(unittest.TestCase):
    """Mixed-content samples vs the independently recomputed reference."""

    SAMPLES = [
        ("pure-english", "The quick brown fox jumps over the lazy dog. " * 40),
        ("pure-chinese", "本技能用于解析中文增值税发票并按月份汇总报销票据。" * 30),
        ("mix-7-3-en-heavy", "Convert CSV exports into formatted Excel workbooks. " * 14
         + "同时支持中文列名的表格。" * 6),
        ("mix-3-7-zh-heavy", "解析上传的中文发票 PDF 文件。" * 40 + "Then export a monthly CSV report. " * 6),
        ("mixed-punct", "步骤：1. 读取文件；2. 提取字段（发票号码、金额）；3. 输出 CSV 汇总表。\n" * 10),
        ("japanese-mixed", "このスキルは日本語の請求書を処理します。Use when the user uploads a PDF. " * 8),
        ("cyrillic-mixed", "Проверка доступа к API. Пользователь запрашивает отчёт. " * 10),
    ]

    def test_all_samples_within_20pct_of_documented_reference(self):
        for label, text in self.SAMPLES:
            est = estimate_tokens(text)
            ref = _reference_tokens(text)
            self.assertGreater(ref, 0, label)
            deviation = abs(est - ref) / ref
            self.assertLessEqual(deviation, 0.20, f"{label}: est={est} ref={ref:.1f}")

    def test_english_baseline_vs_len_quarter_within_20pct(self):
        """English verdicts must not move materially from the W1 heuristic."""
        text = "The quick brown fox jumps over the lazy dog. " * 200
        old = len(text) // 4
        new = estimate_tokens(text)
        self.assertLessEqual(abs(new - old) / old, 0.20)

    def test_chinese_no_longer_underestimated_by_4x(self):
        """The W1 bug: len//4 counted one Chinese char as a quarter token."""
        text = "本技能用于解析中文增值税发票并按月份汇总报销票据。" * 30
        old = len(text) // 4
        new = estimate_tokens(text)
        self.assertGreaterEqual(new / old, 3.0)  # ~4x correction factor

    def test_seven_to_three_mix_within_20pct_of_hand_computed(self):
        # 700 ASCII chars + 300 CJK chars -> reference 0.25*700 + 1.0*300
        text = "a" * 700 + "中" * 300
        est = estimate_tokens(text)
        self.assertEqual(est, 475)
        self.assertLessEqual(abs(est - 475) / 475, 0.20)

    def test_body_tokens_property_uses_shared_estimator(self):
        doc = SkillDoc(body="解析上传的中文发票文件。" * 10)
        self.assertEqual(doc.body_tokens, estimate_tokens(doc.body))
        doc_ascii = SkillDoc(body="x" * 20410)
        self.assertEqual(doc_ascii.body_tokens, 20410 // 4)


class CjkFixtureTests(unittest.TestCase):
    """The Chinese SKILL.md fixture must pass through every relevant rule."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="skillci-cjk-")
        shutil.copytree(FIXTURES / "cjk-skill", Path(tmp) / "cjk-skill")
        cls.tmp = tmp
        cls.docs, cls.findings = lint_path(Path(tmp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def test_chinese_skill_lints_clean(self):
        self.assertEqual(self.findings, [])

    def test_chinese_trigger_hint_suppresses_dq003(self):
        # description contains "当用户...时使用" -> recognized trigger guidance
        self.assertEqual(
            [f.rule_id for f in self.findings if f.rule_id == "DQ003"], []
        )

    def test_body_token_estimate_matches_independent_reference(self):
        self.assertEqual(len(self.docs), 1)
        doc = self.docs[0]
        ref = _reference_tokens(doc.body)
        deviation = abs(doc.body_tokens - ref) / ref
        self.assertLessEqual(deviation, 0.20)
        # and the estimator really applied CJK weighting:
        self.assertGreater(doc.body_tokens, len(doc.body) // 4 * 3)

    def test_chinese_description_length_checked_in_chars(self):
        doc = self.docs[0]
        self.assertGreaterEqual(len(doc.description), 20)
        self.assertLessEqual(len(doc.description), 1024)


class ChineseTriggerHintTests(unittest.TestCase):
    def _lint_text(self, description):
        tmp = tempfile.mkdtemp(prefix="skillci-cjk2-")
        self.addCleanup(shutil.rmtree, tmp, True)
        skill_dir = Path(tmp) / "cn-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: cn-skill\n"
            f"description: {description}\n"
            "---\n"
            "\n正文内容：读取文件，输出表格。\n",
            encoding="utf-8",
        )
        return lint_path(Path(tmp))

    def test_description_without_any_trigger_hint_still_flagged(self):
        _, findings = self._lint_text("解析中文发票，提取号码与金额，输出汇总表格。")
        self.assertIn("DQ003", {f.rule_id for f in findings})

    def test_shi_yong_yu_hint_recognized(self):
        _, findings = self._lint_text("解析中文发票并提取金额字段。适用于需要整理报销票据的场景。")
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
