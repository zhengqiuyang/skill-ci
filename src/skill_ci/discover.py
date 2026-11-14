"""Locate SKILL.md files under a target directory (untrusted content safe:
only paths are collected, files are read as text by the pipeline)."""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    ".scratch",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "dist",
    "build",
}


def find_skill_files(root: Path) -> list[Path]:
    """Return every ``SKILL.md`` (name matched case-insensitively) under root."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for filename in filenames:
            if filename.lower() == "skill.md":
                found.append(Path(dirpath) / filename)
    found.sort()
    return found
