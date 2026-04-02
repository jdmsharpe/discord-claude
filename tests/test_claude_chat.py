from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_usage(**kwargs):
    """Create a mock usage object with proper numeric values and server_tool_use=None."""
    defaults = {
        "input_tokens": 10,
        "output_tokens": 15,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "server_tool_use": None,
    }
    defaults.update(kwargs)
    return MagicMock(**defaults)


class TestCallApiWithToolLoop:
    """Tests for the call_api_with_tool_loop behavior via the cog wrapper."""

    @pytest.fixture
    def cog(self, mock_bot):
        """Create a ClaudeCog instance."""
        with patch("discord_claude.cogs.claude.client.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from discord_claude.cogs.claude.cog import ClaudeCog

            cog = ClaudeCog(bot=mock_bot)
            cog.client = mock_client
            return cog

    async def test_simple_end_turn(self, cog):
        """Single API call with end_turn returns ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        assert len(messages) == 2
        assert messages[1]["role"] == "assistant"
        cog.client.messages.create.assert_called_once()

    async def test_pause_turn_continues(self, cog):
        """pause_turn response causes re-send, then end_turn completes."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = None

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Found it!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None

        cog.client.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [{"role": "user", "content": "Search for something"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Found it!"
        assert cog.client.messages.create.call_count == 2

    async def test_tool_use_loop(self, cog):
        """tool_use triggers execution and re-send."""
        tool_response = MagicMock()
        tool_text = MagicMock()
        tool_text.type = "text"
        tool_text.text = "Let me check."
        tool_text.citations = None
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "memory"
        tool_block.input = {"command": "view", "path": "/memories"}
        tool_response.content = [tool_text, tool_block]
        tool_response.stop_reason = "tool_use"
        tool_response.usage = None

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "No memories found."
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None

        cog.client.messages.create = AsyncMock(side_effect=[tool_response, final_response])

        messages = [{"role": "user", "content": "Check my memories"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        with patch("discord_claude.memory.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "No memory files found."

            parsed = await cog._call_api_with_tool_loop(
                api_params=api_params, messages=messages, user_id=123
            )

        assert parsed.text == "No memories found."
        assert cog.client.messages.create.call_count == 2
        assert len(messages) == 4

    async def test_max_iterations_safety(self, cog):
        """Loop stops at max_iterations."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Still working..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = None

        cog.client.messages.create = AsyncMock(return_value=pause_response)

        messages = [{"role": "user", "content": "Do something"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        await cog._call_api_with_tool_loop(
            api_params=api_params,
            messages=messages,
            user_id=123,
            max_iterations=3,
        )

        assert cog.client.messages.create.call_count == 3

    async def test_max_tokens_stop_reason(self, cog):
        """max_tokens stop reason is propagated on ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Truncated response..."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "max_tokens"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Write a long essay"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 10}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "max_tokens"
        assert parsed.text == "Truncated response..."
        assert len(messages) == 2

    async def test_refusal_stop_reason(self, cog):
        """refusal stop reason is propagated on ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I can't help with that."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "refusal"
        mock_response.stop_details = MagicMock(
            type="refusal",
            category="cyber",
            explanation="This request would facilitate cyber abuse.",
        )
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Bad request"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "refusal"
        assert parsed.stop_details == {
            "type": "refusal",
            "category": "cyber",
            "explanation": "This request would facilitate cyber abuse.",
        }

    async def test_context_window_exceeded_stop_reason(self, cog):
        """model_context_window_exceeded stop reason is propagated."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Partial response..."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "model_context_window_exceeded"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Very long conversation"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 64000}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "model_context_window_exceeded"

    async def test_compaction_model_uses_beta_api(self, cog):
        """Compaction models use client.beta.messages.create with compaction params."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4-6", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "compact-2026-01-12" in call_kwargs["betas"]
        assert {"type": "compact_20260112"} in call_kwargs["context_management"]["edits"]
        assert call_kwargs["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    async def test_non_compaction_model_uses_regular_api(self, cog):
        """Non-compaction models without tools/thinking use client.messages.create."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        cog.client.messages.create.assert_called_once()

    async def test_mcp_uses_beta_api(self, cog):
        """MCP-enabled requests should opt into the MCP beta header."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello from MCP."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "mcp_servers": [{"type": "url", "url": "https://mcp.example.com/sse", "name": "test"}],
            "tools": [{"type": "mcp_toolset", "mcp_server_name": "test"}],
        }

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello from MCP."
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "mcp-client-2025-11-20" in call_kwargs["betas"]


class TestRunChatCommand:
    @pytest.fixture
    def cog(self, mock_bot):
        with patch("discord_claude.cogs.claude.client.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from discord_claude.cogs.claude.cog import ClaudeCog

            cog = ClaudeCog(bot=mock_bot)
            cog.client = mock_client
            return cog

    async def test_chat_rejects_unknown_mcp_preset(self, cog, mock_discord_context, monkeypatch):
        monkeypatch.setattr(
            "discord_claude.cogs.claude.chat.resolve_mcp_presets",
            lambda names: ([], "Unknown MCP preset `bad`."),
        )

        await cog.chat.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello",
            mcp="bad",
        )

        call_kwargs = mock_discord_context.send_followup.call_args[1]
        assert "Unknown MCP preset `bad`." in call_kwargs["embed"].description
        assert cog.client.messages.create.call_args is None

    async def test_context_editing_with_tools(self, cog):
        """Models with tools get context editing via beta API."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "tools": [{"type": "web_search_20260209", "name": "web_search"}],
        }

        await cog._call_api_with_tool_loop(api_params=api_params, messages=messages, user_id=123)

        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "context-management-2025-06-27" in call_kwargs["betas"]
        edits = call_kwargs["context_management"]["edits"]
        tool_edits = [edit for edit in edits if edit["type"] == "clear_tool_uses_20250919"]
        assert len(tool_edits) == 1

    async def test_context_editing_with_thinking(self, cog):
        """Models with thinking get thinking block clearing."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "thinking": {"type": "enabled", "budget_tokens": 5000},
        }

        await cog._call_api_with_tool_loop(api_params=api_params, messages=messages, user_id=123)

        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        edits = call_kwargs["context_management"]["edits"]
        thinking_edits = [edit for edit in edits if edit["type"] == "clear_thinking_20251015"]
        assert len(thinking_edits) == 1
        assert edits[0]["type"] == "clear_thinking_20251015"

    async def test_cache_tokens_accumulated(self, cog):
        """Cache creation and read tokens are accumulated across iterations."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = _make_usage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=0,
        )

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Done!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = _make_usage(
            input_tokens=50,
            output_tokens=30,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=200,
        )

        cog.client.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.input_tokens == 150
        assert parsed.output_tokens == 80
        assert parsed.cache_creation_tokens == 200
        assert parsed.cache_read_tokens == 200

    async def test_server_tool_use_accumulated(self, cog):
        """Server tool use counts are accumulated across iterations."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        server_tool_use_1 = MagicMock(
            web_search_requests=2,
            web_fetch_requests=1,
            code_execution_requests=0,
        )
        pause_response.usage = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=server_tool_use_1,
        )

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Found results!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        server_tool_use_2 = MagicMock(
            web_search_requests=1,
            web_fetch_requests=0,
            code_execution_requests=1,
        )
        final_response.usage = MagicMock(
            input_tokens=200,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=server_tool_use_2,
        )

        cog.client.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [{"role": "user", "content": "Search for something"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.web_search_requests == 3
        assert parsed.web_fetch_requests == 1
        assert parsed.code_execution_requests == 1

    async def test_server_tool_use_none_handled(self, cog):
        """Responses without server_tool_use don't break accumulation."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage()

        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.web_search_requests == 0
        assert parsed.web_fetch_requests == 0
        assert parsed.code_execution_requests == 0

    async def test_context_warning_at_85_percent(self, cog):
        """context_warning is set when input tokens exceed 85% of context window."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(input_tokens=175_000, output_tokens=500)
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_warning is True
        assert parsed.context_compacted is False

    async def test_no_context_warning_below_threshold(self, cog):
        """context_warning is not set when input tokens are below 85%."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(input_tokens=50_000, output_tokens=500)
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_warning is False

    async def test_manual_compaction_triggers_at_75_percent(self, cog):
        """Non-compaction models trigger manual compaction when tokens exceed 75%."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Working..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = _make_usage(input_tokens=155_000, output_tokens=200)

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Done!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = _make_usage(input_tokens=2_000, output_tokens=100)

        summary_response = MagicMock()
        summary_text = MagicMock()
        summary_text.type = "text"
        summary_text.text = "<summary>Conversation summary here.</summary>"
        summary_response.content = [summary_text]

        cog.client.messages.create = AsyncMock(
            side_effect=[pause_response, summary_response, final_response]
        )

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue"},
        ]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_compacted is True
        assert parsed.text == "Done!"
        assert cog.client.messages.create.call_count == 3

    async def test_compaction_model_skips_manual_compaction(self, cog):
        """Compaction models (server-side) never trigger manual compaction."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(input_tokens=180_000, output_tokens=500)
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4-6", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_compacted is False
        assert parsed.context_warning is True
        cog.client.beta.messages.create.assert_called_once()
