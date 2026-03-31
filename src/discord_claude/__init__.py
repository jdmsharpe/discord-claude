"""Top-level namespace providing the Claude cog for easy imports."""

from importlib import metadata

from .cogs.claude.cog import ClaudeCog

__all__ = ["ClaudeCog"]

try:
    __version__ = metadata.version("discord-claude")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"
