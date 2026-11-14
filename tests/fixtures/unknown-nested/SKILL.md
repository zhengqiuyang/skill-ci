---
name: unknown-nested
description: Carries a nested map under an unknown top-level key. Use when unknown keys must stay info-level findings.
x-custom-scope:
  depth: repo
---

# Body

Top-level unknown keys stay FM007 (info) even when their value is a nested
map, and the nested map must not trigger FM001. (`context` itself joined the
known-keys whitelist in W3.1, so this fixture uses a custom key instead.)
