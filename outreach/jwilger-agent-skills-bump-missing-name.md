# Outreach draft 1 — jwilger/agent-skills: `bump` skill is missing `name`

**Status: DRAFT — not sent. Requires lead approval before any contact.**

- **Target repo / maintainer:** `jwilger/agent-skills` (repo owner
  @jwilger). Single-maintainer personal skill collection.
- **Where:** `.claude/skills/bump/SKILL.md`, frontmatter lines 1–10
  (checked against the `main`-branch tarball fetched 2026-11-14).
- **Rule / severity:** FM002 — frontmatter is missing the required `name`
  key (error).

## Problem summary

The `bump` skill's frontmatter has `description`, `user-invocable`,
`argument-hint` and `allowed-tools`, but no `name:` key. The SKILL.md
spec requires `name`; without it, anything that registers or indexes
skills by name (plugin marketplaces, skill routers, linters, the
`.claude/skills` loader conventions) falls back to the directory name or
skips the skill entirely. Every other skill in the repo has `name`, so
this one file is the odd one out — likely just an oversight.

## Suggested fix (one line)

Add the name as the first frontmatter key, matching the directory:

```yaml
---
name: bump
description: INVOKE to bump the project version. Discovers changed skills since last tag, shows confirmation summary, commits per-skill then commits project version, tags, and pushes
user-invocable: true
argument-hint: [major|minor|patch]
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---
```

(`name: bump` matches the parent directory `.claude/skills/bump`, which
is what tools that do check will expect.)

## Tone notes

- Lead with the fact that the rest of the collection is exemplary —
  this is the only FM002 in 21 skills.
- Frame as "found while running a static linter over public skill repos",
  not as a criticism; offer the exact diff so it is a 10-second fix.
- Do not imply the skill is broken at runtime — it may work fine in the
  author's own setup; the issue is interoperability with name-based
  tooling.
