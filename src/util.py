# ruff: noqa: F403

"""Compatibility shim for the relocated util helpers."""

from __future__ import annotations

import warnings

from discord_claude.util import *

warnings.warn(
    "Importing from the legacy util module is deprecated; use discord_claude.util instead.",
    DeprecationWarning,
    stacklevel=2,
)
