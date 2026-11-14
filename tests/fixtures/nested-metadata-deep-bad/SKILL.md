---
name: nested-metadata-deep-bad
description: Breaks a sibling line under a two-level nested mapping. Use when malformed frontmatter must stay FM001.
metadata:
  author:
    name: Example Author
  this line has no colon
---

# Bad

Two-level nesting is tolerated, but a stray sibling line inside the nested
map must stay a loud FM001 parse note.
