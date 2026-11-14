---
name: nested-metadata-deep
description: Stores a two-level nested metadata mapping. Use when deep metadata must parse without FM001.
metadata:
  author:
    name: Example Author
    url: https://example.com/author
  version: "1.0"
---

# Body

`metadata.author` is a depth-2 mapping: allowed (never FM001), stored as a
raw string, and reported as FM008 (info).
