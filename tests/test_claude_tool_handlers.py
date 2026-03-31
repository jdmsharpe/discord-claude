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
