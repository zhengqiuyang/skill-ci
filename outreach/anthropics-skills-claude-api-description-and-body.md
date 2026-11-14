# Outreach draft 2 — anthropics/skills: `claude-api` description over the 1024-char spec limit (+ ~26k-token body)

**Status: DRAFT — not sent. Requires lead approval before any contact.**

- **Target repo / maintainer:** `anthropics/skills` (maintained by
  Anthropic; open a regular issue, no @-ping of individuals).
- **Where:** `skills/claude-api/SKILL.md` — `description: |-` block,
  lines 3–8; body from line 9 (checked against the `main`-branch tarball
  fetched 2026-11-14).
- **Rules / severity:** DQ004 (error) — description is 1068 chars, over
  the 1024-char SKILL.md spec limit; TK002 (error) — body is ~25,995
  estimated tokens, over a 15,000-token "split the skill" threshold
  (script-weighted estimate: ASCII 0.25 tokens/char, CJK 1.0 — a
  budgeting heuristic, not a tokenizer).

## Problem summary

`claude-api` is the single most-referenced skill in the collection, and
it is the only one that breaks both budget rules:

1. The description folds to **1068 chars** (limit 1024). Most consumers
   truncate or reject over-limit descriptions at load time, which would
   silently cut the carefully engineered TRIGGER/SKIP guidance — the
   part doing the disambiguation work.
2. The body is **~26k estimated tokens** across 12 language subdirs'
   worth of inlined reference content. Since `description` is always in
   context and the whole body lands in context on trigger, this one
   skill costs ~26k tokens per invocation; the repo's own best practice
   (and the skill-creator guidance) is progressive disclosure via
   reference files.

## Suggested fix

**Description (proposed rewrite folds to 909 chars, keeps the TRIGGER /
SKIP structure and the grep heuristic):**

```yaml
description: |-
  Reference for the Claude API / Anthropic SDK (model ids, pricing, params, streaming, tool use, MCP, agents, caching, token counting, model migration). TRIGGER - read BEFORE opening the target file whenever: the prompt names Claude/Anthropic in any form (Claude, Anthropic, Opus, Sonnet, Haiku, `anthropic`, `@anthropic-ai`, `claude-*`), the user asks about LLM pricing/model choice/limits/caching (never answer from memory), or the task is LLM-shaped with the provider unstated (agent/MCP/RAG/LLM-judge/tool-calls; generate/summarize/extract/classify/rewrite over NL; debugging refusals/cutoffs/streaming). SKIP when another provider is clearly being worked on (overrides all triggers): OpenAI/GPT/Gemini/Llama/Mistral/Cohere/Ollama named in the query, or a project-wide grep for 'openai|langchain_openai|google.generativeai|genai|mistralai|cohere|ollama' hits (run that grep first when no provider is named).
```

(What was dropped: the `Fable`/`us.anthropic.*`/`[1m]` alias list and
some enumeration detail — worth a maintainer check that no load-bearing
alias was lost.)

**Body:** keep the routing table + per-language "choose your surface"
steps in SKILL.md, and move the per-language reference content that
already exists as subdirectory files behind on-demand reads (the files
are already there — the body mostly duplicates them). That should bring
the triggered context from ~26k tokens to a small fraction.

## Tone notes

- Open by acknowledging this is the best-engineered description in the
  repo — the over-limit is a side effect of that quality, and the fix
  should preserve its structure.
- Flag the token estimate as an estimate (documented heuristic), not a
  tokenizer measurement.
- The description fix is mechanical; the body restructure is a bigger
  call — present it as optional "if you agree the duplication exists".
