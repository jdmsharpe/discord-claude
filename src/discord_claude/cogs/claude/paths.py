"""Paths used by memory tooling."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MEMORIES_BASE_DIR = ROOT_DIR / "memories"

__all__ = ["ROOT_DIR", "MEMORIES_BASE_DIR"]
