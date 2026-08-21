"""Paths used by memory tooling."""

import os
from pathlib import Path

DEFAULT_MEMORIES_BASE_DIR = Path.cwd() / "memories"


def get_memories_base_dir() -> Path:
    """Return configured memory base directory.

    Uses MEMORIES_DIR when set, otherwise falls back to the cwd-relative
    default directory (`./memories`).
    """
    configured = os.getenv("MEMORIES_DIR")
    if not configured:
        return DEFAULT_MEMORIES_BASE_DIR
    return Path(configured).expanduser()


MEMORIES_BASE_DIR = get_memories_base_dir()

__all__ = ["DEFAULT_MEMORIES_BASE_DIR", "MEMORIES_BASE_DIR", "get_memories_base_dir"]
