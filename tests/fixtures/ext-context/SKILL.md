---
name: ext-context
description: Points the host at extra context files. Use when a skill needs additional context loaded.
context:
  files: refs/spec.md
---

# Body

`context` is a Claude Code extension key (2026-11, seen in public skill
repos); a one-level nested map under it parses cleanly and must not be
reported as FM007 or FM001.
