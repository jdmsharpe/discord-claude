# ruff: noqa: F403

"""Compatibility shim for the relocated bash_tool module."""

from __future__ import annotations

import warnings

from discord_claude.bash_tool import *

warnings.warn(
    "Importing from the legacy bash_tool module is deprecated; use discord_claude.bash_tool instead.",
    DeprecationWarning,
    stacklevel=2,
)
