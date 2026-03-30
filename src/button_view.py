"""Compatibility shim for the relocated Anthropic button view."""

from __future__ import annotations

import warnings

from discord_claude.cogs.claude.views import ButtonView

warnings.warn(
    "Importing ButtonView from the root is deprecated; import from discord_claude.cogs.claude.views instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["ButtonView"]
