"""skill-test: trigger-prediction evaluation for skill repositories (W2).

Given a labeled prompt suite (``prompts.jsonl``) and a skill repository,
predict which skill would be triggered for each prompt using a local BM25
index over each skill's ``name`` + ``description`` + ``when_to_use``, plus a
document-matching fallback rule, and report trigger precision/recall with
fully traceable FP/FN evidence.

**No LLM, no real agent runs, no network** -- the predictor is deterministic
stdlib BM25 plus a substring fallback; it measures how well the skill
metadata alone would route a prompt.

prompts.jsonl contract
----------------------
One JSON object per line, exactly two keys::

    {"prompt": "convert this csv to excel", "expected": "csv-to-excel"}
    {"prompt": "what is the capital of France", "expected": null}
    {"prompt": "tell me a joke", "expected": "none"}

- ``prompt``: required, non-empty string.
- ``expected``: required; a skill ``name`` that SHOULD trigger, or
  ``null`` / ``"none"`` (case-insensitive) for prompts that must trigger
  NO skill.
- Unknown skill ids are a usage error (exit 2), never silently ignored.
- Blank lines are skipped; malformed lines are a usage error (exit 2)
  with the 1-based line number.

Metric conventions
------------------
- TP: predicted == expected (expected not null).
- FP: predicted is not null and predicted != expected. (A wrong-skill
  trigger counts as FP for the wrongly-predicted skill and, for
  multi-class precision, appears in both the FP and FN lists.)
- FN: predicted != expected while expected is not null (missed trigger or
  wrong skill).
- TN: expected null and predicted null.
- precision = TP / (TP + FP); recall = TP / (TP + FN); an empty
  denominator is defined as 1.0 (nothing wrong happened - documented
  convention, pinned by tests).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .bm25 import BM25Index, tokenize
from .model import SkillDoc
from .tokens import estimate_tokens

# --- documented predictor constants -------------------------------------
# BM25 must beat this for a skill to be predicted. Calibrated on the
# synthetic W2 suite (see docs/w2-report.md): one rare-term match with
# df=1 in a 5-skill corpus scores ~1.39, generic shared words score < 0.6.
BM25_TRIGGER_THRESHOLD = 1.0
# Fallback rule fires only when BM25 stays below the threshold.
FALLBACK_MIN_PROMPT_CHARS = 8  # avoids trivially short prompts substring-matching

NEGATIVE_EXPECTED = {"none"}


class SuiteError(ValueError):
    """Invalid prompts.jsonl or unknown expected id (rendered as exit 2)."""


@dataclass
class SkillEntry:
    """One indexed skill (id + the metadata fields that feed the router)."""

    skill_id: str
    name: str
    description: str
    when_to_use: str

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.name, self.description, self.when_to_use) if part)


@dataclass
class Prediction:
    prompt: str
    expected: str | None = None
    predicted: str | None = None
    scores: list[tuple[str, float]] = field(default_factory=list)  # top (id, score)
    evidence: list[tuple[str, float]] = field(default_factory=list)  # (term, contribution)
    via_fallback: bool = False


@dataclass
class TestReport:
    predictions: list[Prediction]
    tp: int = 0
    tn: int = 0
    false_positives: list[Prediction] = field(default_factory=list)
    false_negatives: list[Prediction] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + len(self.false_positives)) if (self.tp + len(self.false_positives)) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + len(self.false_negatives)) if (self.tp + len(self.false_negatives)) else 1.0


# ---------------------------------------------------------------------------
# Suite loading (prompts.jsonl contract)
# ---------------------------------------------------------------------------
def load_suite(path: Path) -> list[tuple[str, str | None]]:
    """Parse prompts.jsonl; raises SuiteError with 1-based line numbers."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SuiteError(f"cannot read suite file: {exc}") from exc
    entries: list[tuple[str, str | None]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SuiteError(f"suite line {line_no}: not valid JSON: {exc.msg}") from exc
        if not isinstance(obj, dict) or set(obj) != {"prompt", "expected"}:
            raise SuiteError(
                f"suite line {line_no}: expected an object with exactly the keys "
                "'prompt' and 'expected'"
            )
        prompt, expected = obj["prompt"], obj["expected"]
        if not isinstance(prompt, str) or not prompt.strip():
            raise SuiteError(f"suite line {line_no}: 'prompt' must be a non-empty string")
        if expected is None:
            entries.append((prompt, None))
        elif isinstance(expected, str) and expected.strip().lower() in NEGATIVE_EXPECTED:
            entries.append((prompt, None))
        elif isinstance(expected, str) and expected.strip():
            entries.append((prompt, expected.strip()))
        else:
            raise SuiteError(
                f"suite line {line_no}: 'expected' must be a skill id, null, or \"none\""
            )
    if not entries:
        raise SuiteError("suite contains no prompt entries (empty prompts.jsonl)")
    return entries


def validate_expected(
    entries: list[tuple[str, str | None]], skill_ids: list[str]
) -> None:
    """Every non-null expected id must name an indexed skill."""
    known = set(skill_ids)
    bad: list[str] = []
    for prompt, expected in entries:
        if expected is not None and expected not in known:
            bad.append(f"'{expected}' (prompt: {prompt[:60]}...)" if len(prompt) > 60 else
                       f"'{expected}' (prompt: {prompt})")
    if bad:
        raise SuiteError(
            "suite references unknown skill id(s): " + "; ".join(bad)
            + f". Known ids: {', '.join(sorted(known))}"
        )


# ---------------------------------------------------------------------------
# Skill indexing + prediction
# ---------------------------------------------------------------------------
def skills_from_docs(docs: list[SkillDoc]) -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    for doc in docs:
        skill_id = doc.name
        if not skill_id:
            continue  # nameless/broken skills cannot be triggered by id
        when = doc.frontmatter.get("when_to_use")
        entries.append(
            SkillEntry(
                skill_id=skill_id,
                name=skill_id,
                description=doc.description if isinstance(doc.description, str) else "",
                when_to_use=when if isinstance(when, str) else "",
            )
        )
    entries.sort(key=lambda e: e.skill_id)
    return entries


def _normalize_ws(text: str) -> str:
    return " ".join(text.lower().split())


def predict(
    prompt: str,
    entries: list[SkillEntry],
    index: BM25Index,
    threshold: float = BM25_TRIGGER_THRESHOLD,
) -> Prediction:
    """Predict the triggered skill for one prompt (deterministic)."""
    query_tokens = tokenize(prompt)
    scores = index.search(query_tokens)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    predicted: str | None = None
    via_fallback = False
    evidence: list[tuple[str, float]] = []
    if ranked and ranked[0][1] >= threshold:
        predicted = ranked[0][0]
        evidence = index.explain(query_tokens, predicted)[:3]
    else:
        # Fallback rule: exact document match wins when scoring is too weak.
        prompt_norm = _normalize_ws(prompt)
        candidates: list[str] = []
        for entry in entries:
            entry_norm = _normalize_ws(entry.text)
            if entry_norm and len(prompt_norm) >= FALLBACK_MIN_PROMPT_CHARS \
                    and prompt_norm in entry_norm:
                candidates.append(entry.skill_id)
        if len(candidates) == 1:
            predicted = candidates[0]
            via_fallback = True
            evidence = index.explain(query_tokens, predicted)[:3]
        elif len(candidates) > 1:
            # several documents contain the prompt: highest BM25 among them
            best = max(candidates, key=lambda cid: scores.get(cid, 0.0))
            predicted = best
            via_fallback = True
            evidence = index.explain(query_tokens, best)[:3]

    return Prediction(
        prompt=prompt,
        predicted=predicted,
        scores=[(cid, round(score, 4)) for cid, score in ranked[:3]],
        evidence=evidence,
        via_fallback=via_fallback,
    )


def run_suite(
    entries: list[tuple[str, str | None]],
    skill_entries: list[SkillEntry],
    threshold: float = BM25_TRIGGER_THRESHOLD,
) -> TestReport:
    """Run every labeled prompt through the predictor and score the results."""
    docs_for_index = {e.skill_id: tokenize(e.text) for e in skill_entries}
    index = BM25Index(docs_for_index)
    report = TestReport(predictions=[])
    for prompt, expected in entries:
        prediction = predict(prompt, skill_entries, index, threshold)
        prediction.expected = expected
        report.predictions.append(prediction)
        if expected is None:
            if prediction.predicted is None:
                report.tn += 1
            else:
                report.false_positives.append(prediction)
        else:
            if prediction.predicted == expected:
                report.tp += 1
            else:
                report.false_negatives.append(prediction)
                if prediction.predicted is not None:
                    # wrong skill fired: multi-class FP for that skill
                    report.false_positives.append(prediction)
    return report


def per_skill_distribution(
    entries: list[tuple[str, str | None]], predictions: list[Prediction]
) -> list[dict[str, object]]:
    """Expected vs predicted hit counts per skill id (+ the 'none' class)."""
    ids = sorted({expected for _, expected in entries if expected is not None})
    rows: list[dict[str, object]] = []
    for skill_id in ids:
        expected_hits = sum(1 for _, exp in entries if exp == skill_id)
        predicted_hits = sum(1 for p in predictions if p.predicted == skill_id)
        rows.append(
            {
                "skill_id": skill_id,
                "expected_hits": expected_hits,
                "predicted_hits": predicted_hits,
            }
        )
    rows.append(
        {
            "skill_id": "(none)",
            "expected_hits": sum(1 for _, exp in entries if exp is None),
            "predicted_hits": sum(1 for p in predictions if p.predicted is None),
        }
    )
    return rows


def token_cost(skill_entries: list[SkillEntry]) -> dict[str, object]:
    """Per-skill trigger-metadata token cost (script-weighted estimate)."""
    rows: list[dict[str, object]] = []
    total = 0
    for entry in skill_entries:
        name_t = estimate_tokens(entry.name)
        desc_t = estimate_tokens(entry.description)
        when_t = estimate_tokens(entry.when_to_use)
        row_total = name_t + desc_t + when_t
        total += row_total
        rows.append(
            {
                "skill_id": entry.skill_id,
                "name_tokens": name_t,
                "description_tokens": desc_t,
                "when_to_use_tokens": when_t,
                "total_tokens": row_total,
            }
        )
    return {"per_skill": rows, "suite_total_tokens": total}
