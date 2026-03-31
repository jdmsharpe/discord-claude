from typing import Any

from discord_claude import memory


class MemoryToolHandler:
    """Executes memory tool operations (sync, wrapped as async)."""

    async def execute(self, tool_input: dict[str, Any], user_id: int) -> str:
        return memory.execute_memory_operation(user_id=user_id, tool_input=tool_input)


__all__ = ["MemoryToolHandler"]
