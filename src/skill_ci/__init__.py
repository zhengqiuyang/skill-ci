"""skill-ci: static CI tooling for agent-skill repositories.

Week 1 scope: ``skill-lint`` -- a zero-dependency, stdlib-only static linter
for SKILL.md files (frontmatter, description quality, token cost,
cross-skill duplicates, security hints). No web UI, no network, no LLM calls.

Week 2 additions: script-weighted token estimation (``skill_ci.tokens``),
rule-grouped markdown output with ``--all-instances``, ``bin/`` launchers
(no pip install needed), and ``skill-test`` (``python -m skill_ci test``)
-- deterministic BM25 trigger prediction against a labeled prompts.jsonl
suite with precision/recall/FP/FN reporting. Still zero runtime
dependencies; no network at runtime; no LLM calls.
"""

__version__ = "0.2.0"
