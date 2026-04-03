"""Paths used by memory tooling."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_MEMORIES_BASE_DIR = ROOT_DIR / "memories"


def get_memories_base_dir() -> Path:
    """Return configured memory base directory.

    Uses MEMORIES_DIR when set, otherwise falls back to the repo-local
    default directory.
    """
    configured = os.getenv("MEMORIES_DIR")
    if not configured:
        return DEFAULT_MEMORIES_BASE_DIR
    return Path(configured).expanduser()


MEMORIES_BASE_DIR = get_memories_base_dir()

__all__ = ["ROOT_DIR", "DEFAULT_MEMORIES_BASE_DIR", "MEMORIES_BASE_DIR", "get_memories_base_dir"]
