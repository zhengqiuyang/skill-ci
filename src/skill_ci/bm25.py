"""Minimal stdlib BM25 (Okapi) index for skill trigger prediction (W2).

No third-party dependencies: a plain inverted-term-frequency index with the
standard Okapi scoring:

    score(q, d) = sum_t idf(t) * tf(t, d) * (k1 + 1)
                           / (tf(t, d) + k1 * (1 - b + b * |d| / avgdl))
    idf(t)      = ln(1 + (N - df(t) + 0.5) / (df(t) + 0.5))     # Lucene form,
                                                                # always > 0

Constants (k1, b) are the textbook defaults and are module-level constants
so tests and reports can reference them.
"""

from __future__ import annotations

import math

K1 = 1.5  # Okapi term-frequency saturation
B = 0.75  # Okapi length normalization


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens: [a-z0-9]+ runs plus CJK character bigrams.

    CJK text has no whitespace word boundaries, so consecutive CJK
    characters are emitted as character bigrams (single characters when a
    run has length 1). This is the standard dependency-free CJK indexing
    approach and is what makes Chinese descriptions/prompt matchable.
    """
    lowered = text.lower()
    words: list[str] = []
    buf: list[str] = []
    cjk_run: list[str] = []
    from .tokens import is_cjk_char  # local import: single shared CJK definition

    def flush_word():
        if buf:
            words.append("".join(buf))
            buf.clear()

    def flush_cjk():
        if not cjk_run:
            return
        if len(cjk_run) == 1:
            words.append(cjk_run[0])
        else:
            words.extend(cjk_run[i] + cjk_run[i + 1] for i in range(len(cjk_run) - 1))
        cjk_run.clear()

    for ch in lowered:
        if ch.isascii() and ch.isalnum():
            flush_cjk()
            buf.append(ch)
        elif is_cjk_char(ord(ch)):
            flush_word()
            cjk_run.append(ch)
        else:
            flush_word()
            flush_cjk()
    flush_word()
    flush_cjk()
    return words


class BM25Index:
    """BM25 over a fixed corpus: ``doc_id -> token list``."""

    def __init__(self, docs: dict[str, list[str]]):
        self.doc_ids = sorted(docs)
        self.doc_lens = {doc_id: len(tokens) for doc_id, tokens in docs.items()}
        self.n_docs = len(docs)
        self.avgdl = (
            sum(self.doc_lens.values()) / self.n_docs if self.n_docs else 0.0
        )
        self._docs = docs
        # term -> doc_id -> term frequency
        self._tf: dict[str, dict[str, int]] = {}
        for doc_id, tokens in docs.items():
            for term in tokens:
                self._tf.setdefault(term, {}).setdefault(doc_id, 0)
                self._tf[term][doc_id] += 1

    def idf(self, term: str) -> float:
        df = len(self._tf.get(term, {}))
        if df == 0 or self.n_docs == 0:
            return 0.0
        return math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def _tf_weight(self, term: str, doc_id: str) -> float:
        tf = self._tf.get(term, {}).get(doc_id, 0)
        if tf == 0:
            return 0.0
        dl = self.doc_lens[doc_id]
        denom = tf + K1 * (1.0 - B + B * (dl / self.avgdl if self.avgdl else 0.0))
        return tf * (K1 + 1.0) / denom

    def search(self, query_tokens: list[str]) -> dict[str, float]:
        """Score every document against the query; returns {doc_id: score}.

        Documents with score 0 are omitted (no overlap -> no trigger).
        """
        scores: dict[str, float] = {}
        for doc_id in self.doc_ids:
            total = 0.0
            for term in set(query_tokens):
                total += self.idf(term) * self._tf_weight(term, doc_id)
            if total > 0.0:
                scores[doc_id] = total
        return scores

    def explain(self, query_tokens: list[str], doc_id: str) -> list[tuple[str, float]]:
        """Per-term score contributions for one document, largest first.

        This is the FP/FN traceability mechanism: each prediction can name
        the exact query terms that produced its score and how much each
        term contributed.
        """
        contributions: list[tuple[str, float]] = []
        for term in sorted(set(query_tokens)):
            weight = self.idf(term) * self._tf_weight(term, doc_id)
            if weight > 0.0:
                contributions.append((term, round(weight, 4)))
        contributions.sort(key=lambda pair: pair[1], reverse=True)
        return contributions
