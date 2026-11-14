---
name: list-metadata
description: Stores reviewers as a block list and tags as an inline list inside metadata. Use when nested list values must be verified.
metadata:
  reviewers:
    - alice
    - bob
  tags: [docs, lint]
  requires: []
---

# Body

Block lists, inline lists and empty inline lists all work under metadata.
