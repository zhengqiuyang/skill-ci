---
name: unknown-nested
description: Carries a nested map under an unknown top-level key. Use when unknown keys must stay info-level findings.
context:
  scope: repo
---

# Body

Top-level unknown keys stay FM007 (info) even when their value is a nested
map, and the nested map must not trigger FM001.
