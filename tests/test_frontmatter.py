"""Unit tests for the minimal frontmatter parser."""

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from skill_ci.frontmatter import parse_skill_text  # noqa: E402


class FrontmatterParserTest(unittest.TestCase):
    def test_flat_keys_block_list_and_inline_list(self):
        text = (
            "---\n"
            "name: pdf-tools\n"
            "description: Splits PDFs. Use when the user shares a PDF.\n"
            "allowed-tools:\n"
            "  - Read\n"
            "  - Bash\n"
            "tags: [a, b]\n"
            "---\n"
            "# body\n"
        )
        doc = parse_skill_text(text)
        self.assertTrue(doc.has_frontmatter)
        self.assertEqual(doc.name, "pdf-tools")
        self.assertEqual(doc.frontmatter["allowed-tools"], ["Read", "Bash"])
        self.assertEqual(doc.frontmatter["tags"], ["a", "b"])
        self.assertEqual(doc.key_lines["name"], 2)
        self.assertEqual(doc.body_start_line, 9)
        self.assertEqual(doc.parse_notes, [])

    def test_quoted_values_and_comments(self):
        text = (
            "---\n"
            "# a comment\n"
            "name: 'quoted-name'\n"
            'description: "Double quoted. Use when needed."\n'
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.name, "quoted-name")
        self.assertEqual(doc.description, "Double quoted. Use when needed.")
        self.assertEqual(doc.parse_notes, [])

    def test_no_frontmatter(self):
        text = "# just markdown\n"
        doc = parse_skill_text(text)
        self.assertFalse(doc.has_frontmatter)
        self.assertEqual(doc.body, text)
        self.assertEqual(doc.body_start_line, 1)

    def test_unclosed_frontmatter_reports_note(self):
        text = "---\nname: x\n"
        doc = parse_skill_text(text)
        self.assertFalse(doc.has_frontmatter)
        self.assertTrue(any("never closed" in note for _, note in doc.parse_notes))

    def test_block_scalar_is_joined(self):
        text = (
            "---\n"
            "name: block-scalar\n"
            "description: >\n"
            "  Splits PDF files\n"
            "  for the user.\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.description, "Splits PDF files for the user.")

    def test_unrecognized_line_produces_note_with_line_number(self):
        text = "---\nname: x\njust some text\n---\nbody\n"
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [(3, "unrecognized frontmatter line (expected 'key: value')")])

    def test_duplicate_key_produces_note(self):
        text = "---\nname: a\nname: b\n---\nbody\n"
        doc = parse_skill_text(text)
        self.assertTrue(any("duplicate frontmatter key 'name'" in note for _, note in doc.parse_notes))
        self.assertEqual(doc.name, "b")

    def test_empty_key_parses_as_empty_list(self):
        text = "---\nname: x\ndescription:\n---\nbody\n"
        doc = parse_skill_text(text)
        self.assertEqual(doc.frontmatter["description"], [])
        self.assertIsNone(doc.description)


if __name__ == "__main__":
    unittest.main()
