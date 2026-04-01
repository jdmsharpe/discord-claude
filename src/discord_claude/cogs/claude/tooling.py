from discord_claude.util import ToolHandler

from .tool_handlers import MemoryToolHandler


def default_tool_handlers() -> dict[str, ToolHandler]:
    """Build default tool handlers for a cog instance."""
    return {"memory": MemoryToolHandler()}


__all__ = ["MemoryToolHandler", "default_tool_handlers"]
