# ruff: noqa: F403

"""Compatibility shim for the new discord_claude.memory module."""

from __future__ import annotations

import warnings

from discord_claude.memory import *

warnings.warn(
    "Importing from the legacy memory module is deprecated; use discord_claude.memory instead.",
    DeprecationWarning,
    stacklevel=2,
)
