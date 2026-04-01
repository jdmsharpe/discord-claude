from unittest.mock import patch

import pytest


class TestClaudeToolHandlers:
    """Tests for the tool handler registry pattern."""

    @pytest.fixture
    def cog(self, mock_bot):
        with patch("discord_claude.cogs.claude.client.AsyncAnthropic"):
            from discord_claude.cogs.claude.cog import ClaudeCog

            return ClaudeCog(bot=mock_bot)

    async def test_memory_tool_dispatches(self, cog):
        """Memory tool is dispatched via the registry."""
        with patch("discord_claude.memory.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "Memory result."
            result = await cog._execute_tool(
                "memory", {"command": "view", "path": "/memories"}, user_id=123
            )
        assert result == "Memory result."
        mock_exec.assert_called_once_with(
            user_id=123,
            tool_input={"command": "view", "path": "/memories"},
        )

    async def test_unknown_tool_returns_error(self, cog):
        """Unknown tool names return an error string."""
        result = await cog._execute_tool("nonexistent", {}, user_id=123)
        assert "Error: Unknown tool" in result

    async def test_runtime_registration_and_unregistration(self, cog):
        """Handlers can be registered and unregistered on a cog instance at runtime."""

        class RuntimeHandler:
            async def execute(self, tool_input, user_id):
                return f"runtime:{user_id}:{tool_input['value']}"

        handler = RuntimeHandler()
        cog.register_tool_handler("runtime_tool", handler)

        result = await cog._execute_tool("runtime_tool", {"value": "ok"}, user_id=321)
        assert result == "runtime:321:ok"

        removed = cog.unregister_tool_handler("runtime_tool")
        assert removed is handler
        missing_result = await cog._execute_tool("runtime_tool", {"value": "ok"}, user_id=321)
        assert "Error: Unknown tool" in missing_result

    async def test_dispatch_uses_cog_owned_registry(self, cog):
        """Dispatch uses the cog instance registry, not a module-global mapping."""

        class OverrideMemoryHandler:
            async def execute(self, tool_input, user_id):
                return f"override:{tool_input['command']}:{user_id}"

        cog.register_tool_handler("memory", OverrideMemoryHandler())

        with patch("discord_claude.memory.execute_memory_operation") as mock_exec:
            result = await cog._execute_tool(
                "memory", {"command": "view", "path": "/memories"}, user_id=777
            )

        assert result == "override:view:777"
        mock_exec.assert_not_called()
