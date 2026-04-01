from typing import Any

from discord_claude import memory
from discord_claude.util import ToolHandler


class MemoryToolHandler:
    """Executes memory tool operations (sync, wrapped as async)."""

    async def execute(self, tool_input: dict[str, Any], user_id: int) -> str:
        return memory.execute_memory_operation(user_id=user_id, tool_input=tool_input)


def default_tool_handlers() -> dict[str, ToolHandler]:
    """Build the default per-cog handler registry."""
    return {"memory": MemoryToolHandler()}


__all__ = ["MemoryToolHandler", "default_tool_handlers"]
