---
name: nested-metadata-bad
description: Contains a plain sentence with no colon inside the metadata block. Use when malformed frontmatter must fail loudly.
metadata:
  author: Example Author
  this sentence has no colon at all
---

# Bad

The stray line inside the nested map must stay a loud FM001 parse note.
