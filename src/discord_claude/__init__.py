"""Top-level namespace providing the Claude cog for easy imports."""

import warnings
from functools import cache
from importlib import metadata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cogs.claude.cog import ClaudeCog

__all__ = ["ClaudeCog"]


@cache
def _package_version() -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return metadata.version("discord-claude")
    except metadata.PackageNotFoundError:
        return "0.0.0"


def __getattr__(name: str):
    if name == "ClaudeCog":
        from .cogs.claude import ClaudeCog

        return ClaudeCog
    if name == "__version__":
        return _package_version()
    raise AttributeError(name)
