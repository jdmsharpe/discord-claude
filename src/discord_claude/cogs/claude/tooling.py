from typing import Any

from discord_claude.util import ToolHandler

from .tool_handlers import BashToolHandler, MemoryToolHandler

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "memory": MemoryToolHandler(),
    "bash": BashToolHandler(),
}


async def execute_tool(tool_name: str, tool_input: dict[str, Any], user_id: int) -> str:
    """Execute a client-side tool via the handler registry."""
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Error: Unknown tool '{tool_name}'"
    return await handler.execute(tool_input, user_id)


__all__ = ["BashToolHandler", "MemoryToolHandler", "TOOL_HANDLERS", "execute_tool"]
