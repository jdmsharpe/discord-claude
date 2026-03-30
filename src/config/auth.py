"""Compatibility shim that re-exports the namespaced configuration."""

from __future__ import annotations

import warnings

from discord_claude.config.auth import ANTHROPIC_API_KEY, BOT_TOKEN, GUILD_IDS, SHOW_COST_EMBEDS

warnings.warn(
    "Importing config.auth directly is deprecated; import from discord_claude.config.auth instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["ANTHROPIC_API_KEY", "BOT_TOKEN", "GUILD_IDS", "SHOW_COST_EMBEDS"]
