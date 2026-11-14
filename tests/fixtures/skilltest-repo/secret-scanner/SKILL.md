---
name: secret-scanner
description: Scans repositories for hardcoded credentials and API keys. Use when the user wants to audit a codebase for leaked secrets.
allowed-tools:
  - Grep
  - Read
---

# Secret scanner

1. Grep the tree for credential patterns (keys, tokens, passwords).
2. Report each hit with file and line.
