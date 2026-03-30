"""Top-level namespace providing the Anthropic cog for easy imports."""

from importlib import metadata

from .cogs.claude.cog import AnthropicAPI

__all__ = ["AnthropicAPI"]

try:
    __version__ = metadata.version("discord-claude")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"
