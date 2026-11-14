---
name: nested-block-scalar
description: Stores folded and literal block scalars under metadata entries. Use when nested metadata contains multi-line text.
metadata:
  changelog: >-
    First line.
    Second line.
  literal: |-
    line one
    line two
---

# Body

Both nested block scalars must parse without FM001.
