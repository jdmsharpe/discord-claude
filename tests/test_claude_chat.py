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


def _summary_response(usage, text=None, stop_reason="end_turn"):
    """A summarizer response holding one text block; by default a valid summary."""
    if text is None:
        text = (
            '{"task": "long chat", "key_context": "facts so far", '
            '"current_state": "answered the latest question", '
            '"next_steps": "answer the next question"}'
        )
    response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    response.content = [block]
    response.stop_reason = stop_reason
    response.usage = usage
    return response


def _is_summarizer_call(call) -> bool:
    return "format" in (call.kwargs.get("output_config") or {})


def _route_summarizer(chat_responses, summary):
    """A messages.create side effect: the summarizer call (output_config.format set)
    gets ``summary`` (a response, or an exception to raise); every other call takes
    the next of ``chat_responses``."""
    remaining = iter(chat_responses)

    async def create(**kwargs):
        if "format" in (kwargs.get("output_config") or {}):
            if isinstance(summary, BaseException):
                raise summary
            return summary
        return next(remaining)

    return create


def _summarizer_calls(create_mock):
    return [call for call in create_mock.call_args_list if _is_summarizer_call(call)]


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

    async def test_updates_display_posts_progress_and_sends_beta(self, cog):
        """Under thinking.display "updates" every tool_use iteration's readable text is
        posted through the progress callback and the beta header is sent."""
        tool_response = MagicMock()
        status = MagicMock()
        status.type = "thinking"
        status.thinking = "Checking your memories first."
        tool_text = MagicMock()
        tool_text.type = "text"
        tool_text.text = "Let me look."
        tool_text.citations = None
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "memory"
        tool_block.input = {"command": "view", "path": "/memories"}
        tool_response.content = [status, tool_text, tool_block]
        tool_response.stop_reason = "tool_use"
        tool_response.usage = None

        final_response = MagicMock()
        empty_thinking = MagicMock()
        empty_thinking.type = "thinking"
        empty_thinking.thinking = ""
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Nothing stored."
        final_text.citations = None
        final_response.content = [empty_thinking, final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None

        cog.client.beta.messages.create = AsyncMock(side_effect=[tool_response, final_response])
        progress = AsyncMock()
        messages = [{"role": "user", "content": "Check my memories"}]
        api_params = {
            "model": "claude-fable-5-1",
            "max_tokens": 1024,
            "thinking": {"type": "adaptive", "display": "updates"},
        }

        with patch("discord_claude.memory.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "No memory files found."
            parsed = await cog._call_api_with_tool_loop(
                api_params=api_params,
                messages=messages,
                user_id=123,
                progress_callback=progress,
            )

        assert parsed.text == "Nothing stored."
        assert parsed.thinking == ""
        progress.assert_awaited_once_with("Checking your memories first.\nLet me look.")
        for call in cog.client.beta.messages.create.call_args_list:
            assert "thinking-display-updates-2026-08-18" in call.kwargs["betas"]

    async def test_summarized_display_posts_no_progress(self, cog):
        """The default display is unchanged: no progress posts, no updates beta."""
        tool_response = MagicMock()
        tool_text = MagicMock()
        tool_text.type = "text"
        tool_text.text = "Let me look."
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
        final_text.text = "Nothing stored."
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None
        cog.client.beta.messages.create = AsyncMock(side_effect=[tool_response, final_response])
        progress = AsyncMock()
        api_params = {
            "model": "claude-fable-5-1",
            "max_tokens": 1024,
            "thinking": {"type": "adaptive", "display": "summarized"},
        }

        with patch("discord_claude.memory.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "No memory files found."
            await cog._call_api_with_tool_loop(
                api_params=api_params,
                messages=[{"role": "user", "content": "Check my memories"}],
                user_id=123,
                progress_callback=progress,
            )

        progress.assert_not_awaited()
        for call in cog.client.beta.messages.create.call_args_list:
            assert "thinking-display-updates-2026-08-18" not in call.kwargs["betas"]

    async def test_effort_override_message_sends_per_message_effort_beta(self, cog):
        """An effort-only system message in the history needs the per-message effort beta
        (without it the API 400s: "messages.N.output_config: Extra inputs are not permitted")."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Short answer."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)
        messages = [
            {"role": "user", "content": "Plan it."},
            {"role": "assistant", "content": "1. 2. 3."},
            {"role": "system", "content": [], "output_config": {"effort": "low"}},
            {"role": "user", "content": "Summarize."},
        ]

        await cog._call_api_with_tool_loop(
            api_params={"model": "claude-opus-5", "max_tokens": 1024},
            messages=messages,
            user_id=123,
        )

        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "mid-conversation-output-config-2026-07-01" in call_kwargs["betas"]
        assert call_kwargs["messages"][2] == {
            "role": "system",
            "content": [],
            "output_config": {"effort": "low"},
        }

    @pytest.mark.parametrize(
        "model",
        [
            "claude-opus-5-5",
            "claude-opus-5",
            "claude-fable-5-1",
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
        ],
    )
    async def test_per_message_effort_models_send_the_beta_from_the_first_request(self, cog, model):
        """Probed 2026-09-03 (Discord + API): sending the header only once an override
        exists re-renders the prompt and rewrites the whole cached prefix on that turn
        (write 2,366 / read 0); sent from turn 1, the override turn reads the cache
        (read 2,349 / write 19). So the header is constant for these models."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        await cog._call_api_with_tool_loop(
            api_params={"model": model, "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "mid-conversation-output-config-2026-07-01" in call_kwargs["betas"]

    async def test_models_without_per_message_effort_do_not_send_the_beta(self, cog):
        """Fable 5 rejects per-turn effort, so its header set is unchanged."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        await cog._call_api_with_tool_loop(
            api_params={"model": "claude-fable-5", "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "mid-conversation-output-config-2026-07-01" not in call_kwargs["betas"]

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

    async def test_haiku_5_5_requests_send_the_compaction_beta(self, cog):
        """Haiku 5.5 requests send the compact-2026-01-12 beta, which made the probe
        responses carry usage.iterations, so the price tier is chosen per iterations
        entry. Without iterations a server-tool request is tiered on its summed usage."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        await cog._call_api_with_tool_loop(
            api_params={"model": "claude-haiku-5-5", "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        cog.client.messages.create.assert_not_called()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "compact-2026-01-12" in call_kwargs["betas"]
        assert {"type": "compact_20260112"} in call_kwargs["context_management"]["edits"]

    @pytest.mark.parametrize(
        ("model", "target"),
        [
            ("claude-fable-5-1", "claude-opus-4-8"),
            ("claude-fable-5", "claude-opus-4-8"),
            ("claude-opus-5-5", "claude-opus-4-8"),
            ("claude-opus-5", "claude-opus-4-8"),
            # The API rejects Opus 4.8 as a fallback target for Sonnet 5.5.
            ("claude-sonnet-5-5", "claude-sonnet-5"),
        ],
    )
    async def test_refusal_fallback_models_send_their_fallback_target(self, cog, model, target):
        """Every classifier model that accepts `fallbacks` carries the refusal-fallback beta
        and the one explicit target the API permits for it."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        await cog._call_api_with_tool_loop(
            api_params={"model": model, "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "server-side-fallback-2026-06-01" in call_kwargs["betas"]
        assert call_kwargs["fallbacks"] == [{"model": target}]

    @pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-haiku-5-5"])
    async def test_model_without_fallback_support_sends_no_fallback(self, cog, model):
        """Sonnet 5 has no safety classifier, and Haiku 5.5 has classifiers but rejects the
        `fallbacks` parameter with any value, so neither gets the fallback beta or a
        target."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        await cog._call_api_with_tool_loop(
            api_params={"model": model, "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "server-side-fallback-2026-06-01" not in call_kwargs["betas"]
        assert "fallbacks" not in call_kwargs

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

    async def test_chat_rejects_unsupported_advisor_model(self, cog, mock_discord_context):
        await cog.chat.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello",
            model="claude-opus-4-5",
            advisor=True,
        )

        call_kwargs = mock_discord_context.send_followup.call_args[1]
        assert "Advisor is not supported" in call_kwargs["embed"].description

    async def test_chat_long_response_with_sidecars_uses_embed_batches(
        self, cog, mock_discord_context
    ):
        mock_discord_context.send_followup = AsyncMock(return_value=MagicMock(id=123))
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "R" * 8000
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
            await cog.chat.callback(
                cog,
                ctx=mock_discord_context,
                prompt="Hello",
                model="claude-haiku-4-5",
            )

        assert mock_discord_context.send_followup.await_count > 1
        for call in mock_discord_context.send_followup.await_args_list:
            assert "embeds" in call.kwargs
            assert not str(call.kwargs.get("content", "")).startswith("**Response:**")

    async def test_chat_reports_a_compaction_that_did_not_happen(self, cog, mock_discord_context):
        """When the summarizer returns no summary, the reply carries a "Context Not
        Compacted" embed instead of "Context Compacted"."""
        mock_discord_context.send_followup = AsyncMock(return_value=MagicMock(id=123))
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Answer."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(input_tokens=160_000, output_tokens=100)
        truncated_summary = _summary_response(
            _make_usage(input_tokens=160_100, output_tokens=4_096),
            text='{"task": "long chat", "key_context": "fac',
            stop_reason="max_tokens",
        )
        cog.client.messages.create = AsyncMock(
            side_effect=_route_summarizer([mock_response], truncated_summary)
        )

        with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
            await cog.chat.callback(
                cog,
                ctx=mock_discord_context,
                prompt="Hello",
                model="claude-haiku-4-5",
            )

        titles = []
        for call in mock_discord_context.send_followup.await_args_list:
            embeds = call.kwargs.get("embeds") or [call.kwargs.get("embed")]
            titles.extend(embed.title for embed in embeds if embed is not None)
        assert "Context Not Compacted" in titles
        assert "Context Compacted" not in titles
        assert len(_summarizer_calls(cog.client.messages.create)) == 1

    async def test_follow_up_message_reports_a_compaction_that_did_not_happen(
        self, cog, mock_discord_message
    ):
        """In a follow-up message, a summarizer call that raises keeps the conversation:
        the reply carries the "Context Not Compacted" embed and the history is unchanged
        apart from the new turn."""
        from anthropic import APIConnectionError

        from discord_claude.util import ChatCompletionParameters, Conversation

        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Answer."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(input_tokens=160_000, output_tokens=100)
        cog.client.messages.create = AsyncMock(
            side_effect=_route_summarizer([mock_response], APIConnectionError(request=MagicMock()))
        )
        mock_discord_message.reply = AsyncMock(return_value=MagicMock(id=456))

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            conversation_starter=mock_discord_message.author,
            channel_id=mock_discord_message.channel.id,
            conversation_id=123,
        )
        history = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ]
        conversation = Conversation(params=params, messages=list(history))
        conv_key = (mock_discord_message.author.id, mock_discord_message.channel.id)
        cog.conversations[conv_key] = conversation

        with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
            await cog.handle_new_message_in_conversation(mock_discord_message, conversation)

        titles = []
        for call in mock_discord_message.reply.await_args_list:
            embeds = call.kwargs.get("embeds") or [call.kwargs.get("embed")]
            titles.extend(embed.title for embed in embeds if embed is not None)
        assert "Context Not Compacted" in titles
        assert "Context Compacted" not in titles
        assert "Error" not in titles
        assert cog.conversations[conv_key] is conversation
        assert conversation.messages[:2] == history
        assert len(conversation.messages) == 4  # the new user turn and the reply
        assert len(_summarizer_calls(cog.client.messages.create)) == 1

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

    async def test_advisor_uses_beta_api_without_clear_tool_uses(self, cog):
        """Advisor requests opt into the beta header and skip clear_tool_uses edits."""
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
            "model": "claude-sonnet-4-6",
            "max_tokens": 1024,
            "tools": [
                {
                    "type": "advisor_20260301",
                    "name": "advisor",
                    "model": "claude-opus-4-6",
                    "max_uses": 3,
                }
            ],
        }

        await cog._call_api_with_tool_loop(api_params=api_params, messages=messages, user_id=123)

        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "advisor-tool-2026-03-01" in call_kwargs["betas"]
        context_management = call_kwargs.get("context_management")
        edits = [] if context_management is None else context_management.get("edits", [])
        assert all(edit["type"] != "clear_tool_uses_20250919" for edit in edits)

    async def test_advisor_on_non_compaction_model_uses_beta_api_without_context_management(
        self, cog
    ):
        """Advisor-only Haiku requests should use beta API without context-management edits."""
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
            "tools": [
                {
                    "type": "advisor_20260301",
                    "name": "advisor",
                    "model": "claude-opus-4-6",
                    "max_uses": 3,
                }
            ],
        }

        await cog._call_api_with_tool_loop(api_params=api_params, messages=messages, user_id=123)

        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert call_kwargs["betas"] == ["advisor-tool-2026-03-01"]
        assert call_kwargs.get("context_management") is None

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

    async def test_advisor_iterations_are_accumulated(self, cog):
        """Advisor token usage is tracked from usage.iterations."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(
            iterations=[
                MagicMock(
                    type="message",
                    input_tokens=100,
                    output_tokens=50,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=0,
                ),
                MagicMock(
                    type="advisor_message",
                    input_tokens=250,
                    output_tokens=600,
                    cache_creation_input_tokens=75,
                    cache_read_input_tokens=20,
                ),
                MagicMock(
                    type="message",
                    input_tokens=30,
                    output_tokens=15,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=10,
                ),
            ],
            server_tool_use=None,
        )

        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.input_tokens == 130
        assert parsed.output_tokens == 65
        assert parsed.cache_read_tokens == 10
        assert parsed.advisor_calls == 1
        assert parsed.advisor_input_tokens == 250
        assert parsed.advisor_output_tokens == 600
        assert parsed.advisor_cache_creation_tokens == 75
        assert parsed.advisor_cache_read_tokens == 20

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
        """context_warning is set when the latest prompt, cache reads and writes
        included, exceeds 85% of the context window (850k of Sonnet 4.6's 1M)."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(
            input_tokens=6_000,
            output_tokens=500,
            cache_creation_input_tokens=4_000,
            cache_read_input_tokens=850_000,
        )
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4-6", "max_tokens": 1024}

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

        summary = _summary_response(_make_usage(input_tokens=155_500, output_tokens=800))

        cog.client.messages.create = AsyncMock(
            side_effect=_route_summarizer([pause_response, final_response], summary)
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
        assert len(_summarizer_calls(cog.client.messages.create)) == 1

    @staticmethod
    def _text_response(text: str, stop_reason: str, usage):
        response = MagicMock()
        block = MagicMock()
        block.type = "text"
        block.text = text
        block.citations = None
        response.content = [block]
        response.stop_reason = stop_reason
        response.usage = usage
        return response

    async def test_manual_compaction_counts_cached_prompt_tokens(self, cog):
        """A plain chat turn whose prompt is mostly cache reads still compacts.

        Top-level cache_control reports most of a long history as cache reads, so the
        uncached input_tokens stays small. The trigger uses the full prompt (3k + 150k
        read + 1k written = 154k, past Haiku's 150k), and a turn with one response has
        no follow-up request, so compaction runs after the final response and the next
        user turn starts from the summary.
        """
        cog.client.messages.create = AsyncMock(
            side_effect=_route_summarizer(
                [
                    self._text_response(
                        "Answer.",
                        "end_turn",
                        _make_usage(
                            input_tokens=3_000,
                            output_tokens=400,
                            cache_creation_input_tokens=1_000,
                            cache_read_input_tokens=150_000,
                        ),
                    )
                ],
                _summary_response(_make_usage(input_tokens=154_400)),
            )
        )

        messages = [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ]
        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-haiku-4-5", "max_tokens": 1024},
            messages=messages,
            user_id=123,
        )

        assert parsed.text == "Answer."
        assert parsed.context_compacted is True
        # The history was replaced, so no warning about the old prompt size.
        assert parsed.context_warning is False
        summarizer_calls = _summarizer_calls(cog.client.messages.create)
        assert len(summarizer_calls) == 1
        summarized = summarizer_calls[0].kwargs["messages"]
        assert summarized[-2]["role"] == "assistant"  # the reply is part of the summary
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"].startswith("<summary>")

    async def test_manual_compaction_uses_the_latest_prompt_not_the_turn_total(self, cog):
        """Four 60k-token prompts in one tool loop add up past the 150k trigger before the
        last request, but no single prompt reaches it, so nothing is compacted."""
        responses = [
            self._text_response("Working...", "pause_turn", _make_usage(input_tokens=60_000)),
            self._text_response("Working...", "pause_turn", _make_usage(input_tokens=60_000)),
            self._text_response("Working...", "pause_turn", _make_usage(input_tokens=60_000)),
            self._text_response("Done!", "end_turn", _make_usage(input_tokens=60_000)),
        ]
        cog.client.messages.create = AsyncMock(side_effect=responses)

        messages = [{"role": "user", "content": "Hi"}]
        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-haiku-4-5", "max_tokens": 1024},
            messages=messages,
            user_id=123,
        )

        assert parsed.input_tokens == 240_000
        assert parsed.context_compacted is False
        assert _summarizer_calls(cog.client.messages.create) == []

    async def test_manual_compaction_bills_the_summarizer_call(self, cog):
        """The summarizer call's tokens are added to the turn and billed at
        COMPACTION_SUMMARY_MODEL's rates, not the chat model's. A summary of a
        conversation past the 150k trigger is a prompt over 100,000 tokens, so it bills
        at Haiku 5.5's long-context tier ($0.50 input / $2.50 output)."""
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, calculate_cost

        cog.client.messages.create = AsyncMock(
            side_effect=_route_summarizer(
                [
                    self._text_response(
                        "Answer.",
                        "end_turn",
                        _make_usage(
                            input_tokens=2_000, output_tokens=500, cache_read_input_tokens=160_000
                        ),
                    )
                ],
                _summary_response(_make_usage(input_tokens=162_500, output_tokens=1_200)),
            )
        )

        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-opus-4-5", "max_tokens": 1024},
            messages=[
                {"role": "user", "content": "First question"},
                {"role": "assistant", "content": "First answer"},
                {"role": "user", "content": "Second question"},
            ],
            user_id=123,
        )

        assert parsed.context_compacted is True
        assert parsed.input_tokens == 2_000 + 162_500
        assert parsed.output_tokens == 500 + 1_200
        request_cost, _ = cog._track_daily_cost(123, "claude-opus-4-5", parsed)
        summary_cost = calculate_cost(COMPACTION_SUMMARY_MODEL, 162_500, 1_200, long_context=True)
        assert summary_cost == pytest.approx((162_500 * 0.50 + 1_200 * 2.50) / 1e6)
        expected = (
            calculate_cost("claude-opus-4-5", 2_000, 500, cache_read_tokens=160_000) + summary_cost
        )
        assert request_cost == pytest.approx(expected)

    async def test_refusal_fallback_turn_bills_each_attempt_at_its_models_rates(self, cog):
        """The declined Opus 5.5 attempt bills at Opus 5.5 rates and the Opus 4.8 answer
        at Opus 4.8 rates, instead of the whole turn at the served model's rates."""
        from discord_claude.util import calculate_cost

        response = self._text_response(
            "Answer.",
            "end_turn",
            MagicMock(
                iterations=[
                    MagicMock(
                        type="message",
                        model="claude-opus-5-5",
                        input_tokens=2_000,
                        output_tokens=300,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                    MagicMock(
                        type="fallback_message",
                        model="claude-opus-4-8",
                        input_tokens=2_000,
                        output_tokens=900,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                    ),
                ],
                server_tool_use=None,
            ),
        )
        response.model = "claude-opus-4-8"
        response.stop_details = None
        cog.client.beta.messages.create = AsyncMock(return_value=response)

        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-opus-5-5", "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        assert parsed.served_model == "claude-opus-4-8"
        request_cost, _ = cog._track_daily_cost(123, "claude-opus-5-5", parsed)
        expected = calculate_cost("claude-opus-5-5", 2_000, 300) + calculate_cost(
            "claude-opus-4-8", 2_000, 900
        )
        assert request_cost == pytest.approx(expected)
        assert request_cost != pytest.approx(calculate_cost("claude-opus-4-8", 4_000, 1_200))

    async def test_sonnet_5_5_fallback_bills_the_sonnet_5_answer_at_sonnet_5_rates(self, cog):
        """Sonnet 5.5 falls back to Sonnet 5. Both list $2 / $10, but Sonnet 5.5 reads the
        cache at $0.10 and Sonnet 5 at $0.20, so each attempt's cache reads must bill at
        its own model's rate."""
        from discord_claude.util import calculate_cost

        response = self._text_response(
            "Answer.",
            "end_turn",
            MagicMock(
                iterations=[
                    MagicMock(
                        type="message",
                        model="claude-sonnet-5-5",
                        input_tokens=1_000,
                        output_tokens=0,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=50_000,
                    ),
                    MagicMock(
                        type="fallback_message",
                        model="claude-sonnet-5",
                        input_tokens=1_000,
                        output_tokens=700,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=50_000,
                    ),
                ],
                server_tool_use=None,
            ),
        )
        response.model = "claude-sonnet-5"
        response.stop_details = None
        cog.client.beta.messages.create = AsyncMock(return_value=response)

        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-sonnet-5-5", "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        assert parsed.served_model == "claude-sonnet-5"
        assert cog.client.beta.messages.create.call_args.kwargs["fallbacks"] == [
            {"model": "claude-sonnet-5"}
        ]
        request_cost, _ = cog._track_daily_cost(123, "claude-sonnet-5-5", parsed)
        expected = calculate_cost(
            "claude-sonnet-5-5", 1_000, 0, cache_read_tokens=50_000
        ) + calculate_cost("claude-sonnet-5", 1_000, 700, cache_read_tokens=50_000)
        assert request_cost == pytest.approx(expected)
        # $0.10 / MTok for the declined attempt's reads, $0.20 / MTok for the answer's.
        assert expected == pytest.approx(
            (1_000 * 2 + 50_000 * 0.10) / 1e6 + (1_000 * 2 + 700 * 10 + 50_000 * 0.20) / 1e6
        )

    async def test_haiku_5_5_price_tier_is_chosen_per_request(self, cog):
        """Haiku 5.5 bills a request at $0.50 / $2.50 when its own prompt (input + cache
        reads + cache writes) is over 100,000 tokens. The tool loop sends several
        requests per turn: two 60,000-token prompts add up past the threshold but each
        bills at $0.10 / $0.50; only the third, 101,000 tokens with cache reads included,
        bills at the higher prices."""
        from discord_claude.util import calculate_cost

        responses = [
            self._text_response("Working...", "pause_turn", _make_usage(input_tokens=60_000)),
            self._text_response("Working...", "pause_turn", _make_usage(input_tokens=60_000)),
            self._text_response(
                "Done!",
                "end_turn",
                _make_usage(
                    input_tokens=1_000,
                    output_tokens=2_000,
                    cache_read_input_tokens=95_000,
                    cache_creation_input_tokens=5_000,
                ),
            ),
        ]
        cog.client.beta.messages.create = AsyncMock(side_effect=responses)

        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-haiku-5-5", "max_tokens": 1024},
            messages=[{"role": "user", "content": "Hi"}],
            user_id=123,
        )

        request_cost, _ = cog._track_daily_cost(123, "claude-haiku-5-5", parsed)
        standard = calculate_cost("claude-haiku-5-5", 120_000, 30)
        long_context = calculate_cost(
            "claude-haiku-5-5",
            1_000,
            2_000,
            cache_creation_tokens=5_000,
            cache_read_tokens=95_000,
            long_context=True,
        )
        assert request_cost == pytest.approx(standard + long_context)
        assert standard == pytest.approx((120_000 * 0.10 + 30 * 0.50) / 1e6)
        assert long_context == pytest.approx(
            (1_000 * 0.50 + 2_000 * 2.50 + 5_000 * 1.00 + 95_000 * 0.05) / 1e6
        )

    async def test_manual_compaction_without_a_summary_keeps_the_history(self, cog):
        """When the summarizer returns no structured summary (here a refusal written as
        prose), the history is kept, the reply reports that compaction did not happen,
        and the summarizer is not called again in the same turn."""
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, ModelTokenUsage

        responses = [
            self._text_response("Working...", "pause_turn", _make_usage(input_tokens=155_000)),
            self._text_response("Done!", "end_turn", _make_usage(input_tokens=156_000)),
        ]
        refusal = _summary_response(
            _make_usage(input_tokens=155_500, output_tokens=0),
            text="I can't help summarize this.",
            stop_reason="refusal",
        )
        cog.client.messages.create = AsyncMock(side_effect=_route_summarizer(responses, refusal))

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue"},
        ]
        parsed = await cog._call_api_with_tool_loop(
            api_params={"model": "claude-haiku-4-5", "max_tokens": 1024},
            messages=messages,
            user_id=123,
        )

        assert parsed.text == "Done!"
        assert parsed.context_compacted is False
        assert parsed.compaction_failed is True
        assert len(_summarizer_calls(cog.client.messages.create)) == 1
        # The declined summarizer call is billed like every declined attempt, at the
        # summarizer's long-context tier (its prompt is over 100,000 tokens).
        assert parsed.input_tokens == 155_000 + 156_000 + 155_500
        assert parsed.long_context_tokens_by_model == {
            COMPACTION_SUMMARY_MODEL: ModelTokenUsage(input_tokens=155_500)
        }
        assert messages[:3] == [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue"},
        ]
        assert len(messages) == 5  # both assistant replies appended, nothing removed

    async def test_compaction_model_skips_manual_compaction(self, cog):
        """Compaction models (server-side) never trigger manual compaction."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage(input_tokens=900_000, output_tokens=500)
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4-6", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_compacted is False
        assert parsed.context_warning is True
        cog.client.beta.messages.create.assert_called_once()

    @pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-opus-5"])
    async def test_opus_5_uses_server_side_compaction(self, cog, model):
        """Opus 5 / 5.5 (1M window) take the compact beta, never the Haiku-bounded manual path.

        The first turn reports 155k input tokens, past the 150k manual trigger
        that would fire for a non-compaction model; the second call must still
        go out with the compaction edit and without a summarizer pass.
        """
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
        final_response.usage = _make_usage(input_tokens=156_000, output_tokens=100)

        cog.client.beta.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue"},
        ]
        api_params = {"model": model, "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Done!"
        assert parsed.context_compacted is False
        assert cog.client.beta.messages.create.call_count == 2
        assert _summarizer_calls(cog.client.messages.create) == []
        for call in cog.client.beta.messages.create.call_args_list:
            assert "compact-2026-01-12" in call.kwargs["betas"]
            assert {"type": "compact_20260112"} in call.kwargs["context_management"]["edits"]


class TestEffortChange:
    """apply_effort_change / current_effort / the /claude effort command."""

    @pytest.fixture
    def cog(self, mock_bot):
        with patch("discord_claude.cogs.claude.client.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from discord_claude.cogs.claude.cog import ClaudeCog

            cog = ClaudeCog(bot=mock_bot)
            cog.client = mock_client
            return cog

    @staticmethod
    def _conversation(model: str, effort: str | None = None):
        from discord_claude.util import ChatCompletionParameters, Conversation

        params = ChatCompletionParameters(model=model, effort=effort, conversation_id=1)
        return Conversation(params=params, messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"])
    def test_per_message_models_get_an_effort_override_message(self, model):
        from discord_claude.cogs.claude.chat import apply_effort_change, current_effort

        conversation = self._conversation(model, effort="high")

        assert apply_effort_change(conversation, "low") is None
        assert conversation.messages[-1] == {
            "role": "system",
            "content": [],
            "output_config": {"effort": "low"},
        }
        # The top-level effort (and so the cached prefix) is unchanged.
        assert conversation.params.effort == "high"
        assert current_effort(conversation) == "low"

    def test_consecutive_changes_replace_the_trailing_override(self):
        from discord_claude.cogs.claude.chat import apply_effort_change

        conversation = self._conversation("claude-opus-5")
        apply_effort_change(conversation, "medium")
        apply_effort_change(conversation, "max")

        overrides = [m for m in conversation.messages if m.get("role") == "system"]
        assert overrides == [{"role": "system", "content": [], "output_config": {"effort": "max"}}]

    def test_other_models_change_the_top_level_effort(self):
        """Fable 5 400s on per-message effort, so it (and every non-beta model) gets the
        top-level value changed instead — cache reset, but the effort still applies."""
        from discord_claude.cogs.claude.chat import apply_effort_change, current_effort

        conversation = self._conversation("claude-fable-5", effort="high")

        assert apply_effort_change(conversation, "low") is None
        assert conversation.params.effort == "low"
        assert all(m.get("role") != "system" for m in conversation.messages)
        assert current_effort(conversation) == "low"

    def test_unsupported_levels_are_rejected_without_modifying_the_conversation(self):
        from discord_claude.cogs.claude.chat import apply_effort_change

        opus_4_5 = self._conversation("claude-opus-4-5", effort="high")
        error = apply_effort_change(opus_4_5, "max")
        assert error is not None and "`max`" in error and "`high`" in error
        assert opus_4_5.params.effort == "high"
        assert len(opus_4_5.messages) == 1

        haiku = self._conversation("claude-haiku-4-5")
        error = apply_effort_change(haiku, "low")
        assert error is not None and "does not support the `effort` parameter" in error

    async def test_effort_command_without_conversation_errors(self, cog, mock_discord_context):
        await cog.effort.callback(cog, ctx=mock_discord_context, effort="low")

        embed = mock_discord_context.respond.call_args.kwargs["embed"]
        assert embed.title == "Error"
        assert "no active conversation" in embed.description

    async def test_effort_command_updates_the_active_conversation(self, cog, mock_discord_context):
        conversation = self._conversation("claude-opus-5", effort="high")
        key = (mock_discord_context.author.id, mock_discord_context.channel.id)
        cog.conversations[key] = conversation

        await cog.effort.callback(cog, ctx=mock_discord_context, effort="low")

        embed = mock_discord_context.respond.call_args.kwargs["embed"]
        assert embed.title == "Effort Updated"
        assert "`low`" in embed.description
        assert "per message" in embed.description
        assert conversation.messages[-1]["output_config"] == {"effort": "low"}

    async def test_effort_command_reports_unsupported_level(self, cog, mock_discord_context):
        conversation = self._conversation("claude-opus-4-5", effort="high")
        key = (mock_discord_context.author.id, mock_discord_context.channel.id)
        cog.conversations[key] = conversation

        await cog.effort.callback(cog, ctx=mock_discord_context, effort="xhigh")

        embed = mock_discord_context.respond.call_args.kwargs["embed"]
        assert embed.title == "Unsupported Effort"
        assert conversation.params.effort == "high"
