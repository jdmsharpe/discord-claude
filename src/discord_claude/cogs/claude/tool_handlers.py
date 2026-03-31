from typing import Any

from discord_claude import bash_tool, memory


class MemoryToolHandler:
    """Executes memory tool operations (sync, wrapped as async)."""

    async def execute(self, tool_input: dict[str, Any], user_id: int) -> str:
        return memory.execute_memory_operation(user_id=user_id, tool_input=tool_input)


class BashToolHandler:
    """Executes bash tool operations."""

    async def execute(self, tool_input: dict[str, Any], user_id: int) -> str:
        if tool_input.get("restart"):
            return "Bash session restarted."
        command = tool_input.get("command", "")
        if not command:
            return "Error: No command provided."
        return await bash_tool.execute_bash_command(command)


__all__ = ["BashToolHandler", "MemoryToolHandler"]
