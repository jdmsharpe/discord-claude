from typing import Any

from discord_claude.util import ToolHandler

from .tool_handlers import MemoryToolHandler

# Deprecated module-level registry retained for compatibility with older imports.
TOOL_HANDLERS: dict[str, ToolHandler] = {}


async def execute_tool(tool_name: str, tool_input: dict[str, Any], user_id: int) -> str:
    """Deprecated module-level tool dispatcher.

    Prefer using ``ClaudeCog._execute_tool`` and per-cog handler registration.
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Error: Unknown tool '{tool_name}'"
    return await handler.execute(tool_input, user_id)


def default_tool_handlers() -> dict[str, ToolHandler]:
    """Build default tool handlers for a cog instance."""
    return {"memory": MemoryToolHandler()}


__all__ = ["MemoryToolHandler", "TOOL_HANDLERS", "default_tool_handlers", "execute_tool"]
