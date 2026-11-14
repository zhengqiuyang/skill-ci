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


class W3RegressionParserTest(unittest.TestCase):
    """W3.0 regression net: W1/W2 parse behavior that must survive the
    one-level nested-mapping change unchanged."""

    def test_literal_block_scalar_folds_continuation_lines(self):
        text = (
            "---\n"
            "name: pipe-skill\n"
            "description: |\n"
            "  Line one.\n"
            "  Line two.\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.description, "Line one. Line two.")
        self.assertEqual(doc.parse_notes, [])

    def test_block_list_resumes_top_level_keys_after_dedent(self):
        text = (
            "---\n"
            "name: list-resume\n"
            "allowed-tools:\n"
            "  - Read\n"
            "  - Bash\n"
            "license: MIT\n"
            "description: Resumes top-level keys after a block list. Use when lists end.\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.frontmatter["allowed-tools"], ["Read", "Bash"])
        self.assertEqual(doc.frontmatter["license"], "MIT")
        self.assertEqual(doc.parse_notes, [])

    def test_indented_garbage_under_empty_key_is_note(self):
        text = (
            "---\n"
            "name: empty-key-garbage\n"
            "metadata:\n"
            "  just some text without a colon\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(len(doc.parse_notes), 1)
        self.assertEqual(doc.parse_notes[0][0], 4)  # file line of the stray text


class NestedMetadataParserTest(unittest.TestCase):
    """W3.0: one-level nested mappings (notably under ``metadata:``)."""

    def test_nested_metadata_map_parses_to_dict(self):
        text = (
            "---\n"
            "name: nested-meta\n"
            "description: Nested metadata with scalar values. Use when nesting is parsed.\n"
            "metadata:\n"
            "  author: Example Author\n"
            '  version: "1.2.0"\n'
            "  stars: 42\n"
            "  related-skills: pdf-tools, csv-tools\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(
            doc.frontmatter["metadata"],
            {
                "author": "Example Author",
                "version": "1.2.0",
                "stars": "42",  # scalar subset: no type coercion, values stay strings
                "related-skills": "pdf-tools, csv-tools",
            },
        )
        self.assertEqual(doc.key_lines["metadata"], 4)
        self.assertEqual(doc.body_start_line, 10)

    def test_nested_metadata_quotes_are_stripped(self):
        text = (
            "---\n"
            "name: quoted-meta\n"
            "metadata:\n"
            "  author: 'Single Quoted'\n"
            '  version: "1.0.0"\n'
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(
            doc.frontmatter["metadata"],
            {"author": "Single Quoted", "version": "1.0.0"},
        )

    def test_nested_metadata_block_and_inline_lists(self):
        text = (
            "---\n"
            "name: list-meta\n"
            "metadata:\n"
            "  reviewers:\n"
            "    - alice\n"
            "    - bob\n"
            "  tags: [docs, lint]\n"
            "  requires: []\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(
            doc.frontmatter["metadata"],
            {"reviewers": ["alice", "bob"], "tags": ["docs", "lint"], "requires": []},
        )

    def test_empty_metadata_stays_empty_list(self):
        text = "---\nname: empty-meta\nmetadata:\n---\nbody\n"
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(doc.frontmatter["metadata"], [])

    def test_two_level_nesting_is_allowed_but_raw_string(self):
        text = (
            "---\n"
            "name: deep-meta\n"
            "metadata:\n"
            "  author:\n"
            "    name: Jeff\n"
            "    url: https://example.com/jeff\n"
            "  version: \"1.0\"\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(
            doc.frontmatter["metadata"]["author"],
            "name: Jeff\nurl: https://example.com/jeff",
        )
        self.assertEqual(doc.frontmatter["metadata"]["version"], "1.0")

    def test_duplicate_nested_subkey_is_note_and_last_wins(self):
        text = (
            "---\n"
            "name: dup-meta\n"
            "metadata:\n"
            "  author: first\n"
            "  author: second\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(len(doc.parse_notes), 1)
        line, note = doc.parse_notes[0]
        self.assertEqual(line, 5)
        self.assertIn("duplicate key 'author' under 'metadata'", note)
        self.assertEqual(doc.frontmatter["metadata"]["author"], "second")

    def test_unknown_metadata_subkeys_are_allowed(self):
        text = (
            "---\n"
            "name: flavor-meta\n"
            "metadata:\n"
            "  flavor: banana\n"
            "  custom-field: whatever\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(doc.frontmatter["metadata"]["flavor"], "banana")

    def test_unrecognized_line_inside_nested_map_is_note(self):
        text = (
            "---\n"
            "name: bad-meta\n"
            "metadata:\n"
            "  author: Example\n"
            "  this sentence has no colon at all\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(len(doc.parse_notes), 1)
        self.assertEqual(doc.parse_notes[0][0], 5)
        self.assertIn("unrecognized frontmatter line", doc.parse_notes[0][1])

    def test_stray_line_inside_nested_list_value_is_note(self):
        text = (
            "---\n"
            "name: bad-meta-list\n"
            "metadata:\n"
            "  reviewers:\n"
            "    - alice\n"
            "    stray line with no dash\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(len(doc.parse_notes), 1)
        self.assertEqual(doc.parse_notes[0][0], 6)
        self.assertIn("inside list value of 'reviewers' under 'metadata'", doc.parse_notes[0][1])

    def test_nested_map_under_unknown_top_level_key_parses(self):
        text = (
            "---\n"
            "name: unknown-nested\n"
            "context:\n"
            "  scope: repo\n"
            "---\n"
            "body\n"
        )
        doc = parse_skill_text(text)
        self.assertEqual(doc.parse_notes, [])
        self.assertEqual(doc.frontmatter["context"], {"scope": "repo"})


if __name__ == "__main__":
    unittest.main()
