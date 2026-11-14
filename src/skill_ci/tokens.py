"""Script-weighted token estimator (W2).

W1 used ``len(text) // 4``, which assumes English-like density of roughly
4 ASCII characters per token and *severely underestimates* CJK content
(one Chinese character carries roughly one token in mainstream BPE
tokenizers, not one quarter of one).

W2 replaces it with a deterministic, documentable per-script weighted sum.
The estimator is a single shared function: the TK001/TK002 lint thresholds,
the skill inventory, and the ``skill-test`` token-cost section all read the
same number (one口径).

Documented reference weights (tokens per character)
---------------------------------------------------
- ASCII (U+0000-U+007F): 0.25 tokens/char.
  Rationale: mainstream BPE tokenizers average ~4 chars/token on English
  prose; 0.25 keeps pure-ASCII estimates exactly equal to the W1
  ``len//4`` heuristic (floor of 0.25 * n), so no English text changes
  its lint verdict in W2.
- CJK tier: 1.0 tokens/char, applied to:
    * CJK unified ideographs (U+3400-U+4DBF ext A, U+4E00-U+9FFF core,
      U+F900-U+FAFF compatibility, U+20000-U+323AF ext B..F)
    * CJK symbols and punctuation (U+3000-U+303F)
    * Hiragana / Katakana (U+3040-U+30FF)
    * Hangul compatibility jamo (U+3130-U+318F) and syllables (U+AC00-U+D7AF)
    * fullwidth forms (U+FF00-U+FFEF)
  Rationale: public cl100k/o200k tokenizer analyses report roughly
  0.7-1.5 tokens per Chinese character, ~1 per kana, ~1 per Hangul
  syllable. 1.0 is the conservative central value: it never lets a
  budget check *underestimate* CJK content the way len//4 did
  (~4x under).

  Hangul is deliberately weighted like ideographs (not dumped into the
  "other" tier): its real per-char cost is much closer to CJK ideographs
  than to Cyrillic, and under-weighting it would repeat the W1 bug for
  Korean skills.
- Other non-ASCII (Cyrillic, Greek, Arabic, Hebrew, Thai, symbols, emoji,
  ...): 0.5 tokens/char.
  Rationale: Cyrillic/Greek/Arabic word-piece merges run ~0.3-0.6
  tokens/char in the same public analyses; 0.5 is the midpoint. Emoji are
  known to cost ~1-3 tokens each and are accepted as an under-estimate
  for this tier (documented limitation, no skill corpus in scope uses
  them in bulk).

Calibration status (honesty note, see docs/w2-report.md): this is a
deterministic heuristic *self-consistency calibration* against the
documented weights above; it is NOT a measured tokenizer accuracy. Real
tokenizer validation is deferred to W3 (requires network access).
"""

from __future__ import annotations

ASCII_TOKENS_PER_CHAR = 0.25
CJK_TOKENS_PER_CHAR = 1.0
OTHER_TOKENS_PER_CHAR = 0.5

# Inclusive character-range pairs for the CJK-weighted tier (kept as plain
# tuples of ints: no runtime dependencies, cheap membership test).
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x3000, 0x303F),   # CJK symbols and punctuation
    (0x3040, 0x30FF),   # Hiragana + Katakana
    (0x3130, 0x318F),   # Hangul compatibility jamo
    (0x3400, 0x4DBF),   # CJK unified ideographs extension A
    (0x4E00, 0x9FFF),   # CJK unified ideographs (core)
    (0xAC00, 0xD7AF),   # Hangul syllables
    (0xF900, 0xFAFF),   # CJK compatibility ideographs
    (0xFF00, 0xFFEF),   # fullwidth and halfwidth forms
    (0x20000, 0x323AF), # CJK ideographs extensions B..F (supplementary)
)


def is_cjk_char(code_point: int) -> bool:
    """True when the code point belongs to the CJK-weighted tier."""
    return any(lo <= code_point <= hi for lo, hi in _CJK_RANGES)


def tier_counts(text: str) -> tuple[int, int, int]:
    """Return (ascii_chars, cjk_chars, other_chars) for ``text``."""
    n_ascii = n_cjk = n_other = 0
    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            n_ascii += 1
        elif is_cjk_char(cp):
            n_cjk += 1
        else:
            n_other += 1
    return n_ascii, n_cjk, n_other


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: floor of the per-script weighted sum.

    For pure-ASCII text this is exactly ``len(text) // 4`` (the W1
    heuristic), so English-only documents keep their W1 verdicts. For
    pure-CJK text it is one token per character (the documented
    conservative central value).
    """
    n_ascii, n_cjk, n_other = tier_counts(text)
    return int(
        ASCII_TOKENS_PER_CHAR * n_ascii
        + CJK_TOKENS_PER_CHAR * n_cjk
        + OTHER_TOKENS_PER_CHAR * n_other
    )
