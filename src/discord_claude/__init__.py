"""Top-level namespace providing the Claude cog for easy imports."""

from importlib import metadata

__all__ = ["ClaudeCog"]


def __getattr__(name: str):
    if name == "ClaudeCog":
        from .cogs.claude import ClaudeCog

        return ClaudeCog
    raise AttributeError(name)

try:
    __version__ = metadata.version("discord-claude")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"
