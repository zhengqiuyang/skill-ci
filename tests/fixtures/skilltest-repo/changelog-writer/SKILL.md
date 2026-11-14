---
name: changelog-writer
description: Generates release notes from git commit history. Use when the user prepares a release and asks for a changelog.
allowed-tools:
  - Bash
  - Write
---

# Changelog writer

1. Collect commits since the previous tag.
2. Group them into added/changed/fixed and write release notes.
