# Outreach draft 3 — starslingdev/skills: `ci-speedup` body ~9.5k tokens (budget 5k), same pattern in `ci-secure` and `sling`

**Status: DRAFT — not sent. Requires lead approval before any contact.**

- **Target repo / maintainer:** `starslingdev/skills` (repo owner per
  GitHub; no @-ping of individuals in the first contact).
- **Where:** `skills/ci-speedup/SKILL.md` — body starts line 17; the
  file is 515 lines (checked against the `main`-branch tarball fetched
  2026-11-14).
- **Rule / severity:** TK001 (warning) — body is ~9,524 estimated
  tokens, over the 5,000-token recommended budget (script-weighted
  estimate: ASCII 0.25 tokens/char — a budgeting heuristic, not a
  tokenizer).

## Problem summary

`ci-speedup` audits GitHub Actions workflows against a 98-pattern
catalog, and all 98 patterns are inlined in the SKILL.md body. At ~9.5k
estimated tokens it is ~2x the recommended budget — every trigger of the
skill pays the full catalog cost even when the audit only needs a
handful of pattern families. Two sibling skills share the same shape:
`ci-secure` (~7.7k tokens) and `sling` (~8.3k tokens), so this is a
consistent house style rather than a one-off.

## Suggested fix

Progressive disclosure, keeping the SKILL.md as the router:

```markdown
---
name: ci-speedup
description: >-
  (unchanged — the current description is well within limits and does its
  job)
license: MIT
---

# ci-speedup — CI Optimization Audit for GitHub Actions

(keep here: the audit workflow, severity model, report format, and the
pattern-family index — one line per family)

## Pattern catalog (read on demand)

- Caching patterns (14): read `references/patterns-caching.md`
- Redundancy patterns (11): read `references/patterns-redundancy.md`
- Parallelization (9): read `references/patterns-parallelization.md`
- ... (~60 more, one line each)
```

Each audit run then loads only the families it needs, and the
SKILL.md body drops to roughly the budget. The 98-pattern content
moves verbatim — no rewriting, just relocation into
`references/patterns-*.md`.

## Tone notes

- The description is genuinely good (scoped triggers, explicit
  non-goals pointing at `ci-secure`) — say so; the finding is only about
  body size.
- Present the numbers as estimates from a documented heuristic.
- Note the same pattern in `ci-secure`/`sling` as "if you agree the
  split is right, it likely applies there too" — not as a list of
  demands.
