from unittest.mock import MagicMock

import pytest

from discord_claude.util import (
    CHUNK_TEXT_SIZE,
    DISCORD_EMBED_TOTAL_LIMIT,
    MODEL_CONTEXT_WINDOWS,
    ChatCompletionParameters,
    Conversation,
    UsageTotals,
    available_embed_space,
    calculate_cost,
    chunk_text,
    format_anthropic_error,
    truncate_text,
)


class TestChunkText:
    """Tests for the chunk_text function."""

    def test_short_text_single_chunk(self):
        """Short text should return a single chunk."""
        text = "Hello, world!"
        result = chunk_text(text)
        assert result == ["Hello, world!"]

    def test_exact_chunk_size(self):
        """Text exactly at chunk size should return one chunk."""
        text = "a" * CHUNK_TEXT_SIZE
        result = chunk_text(text)
        assert len(result) == 1
        assert result[0] == text

    def test_text_splits_into_multiple_chunks(self):
        """Text longer than chunk size should split into multiple chunks."""
        text = "a" * (CHUNK_TEXT_SIZE * 2 + 100)
        result = chunk_text(text)
        assert len(result) == 3
        assert len(result[0]) == CHUNK_TEXT_SIZE
        assert len(result[1]) == CHUNK_TEXT_SIZE
        assert len(result[2]) == 100

    def test_custom_chunk_size(self):
        """Custom chunk size should be respected."""
        text = "Hello, world! This is a test."
        result = chunk_text(text, chunk_size=10)
        assert len(result) == 3
        assert result[0] == "Hello, wor"
        assert result[1] == "ld! This i"
        assert result[2] == "s a test."

    def test_empty_string(self):
        """Empty string should return empty list."""
        result = chunk_text("")
        assert result == []


class TestTruncateText:
    """Tests for the truncate_text function."""

    def test_short_text_unchanged(self):
        """Text shorter than max_length should be unchanged."""
        text = "Hello"
        result = truncate_text(text, 10)
        assert result == "Hello"

    def test_exact_length_unchanged(self):
        """Text at exact max_length should be unchanged."""
        text = "Hello"
        result = truncate_text(text, 5)
        assert result == "Hello"

    def test_long_text_truncated(self):
        """Text longer than max_length should be truncated with suffix."""
        text = "Hello, world!"
        result = truncate_text(text, 8)
        assert result == "Hello, w..."

    def test_custom_suffix(self):
        """Custom suffix should be used."""
        text = "Hello, world!"
        result = truncate_text(text, 8, suffix="[cut]")
        assert result == "Hello, w[cut]"

    def test_none_returns_none(self):
        """None input should return None."""
        result = truncate_text(None, 10)
        assert result is None


class TestFormatAnthropicError:
    """Tests for the format_anthropic_error function."""

    def test_basic_exception(self):
        """Basic exception should format correctly."""
        error = Exception("Something went wrong")
        result = format_anthropic_error(error)
        assert "Something went wrong" in result

    def test_exception_with_status_code(self):
        """Exception with status_code attribute should include it."""
        error = Exception("API error")
        error.status_code = 429
        result = format_anthropic_error(error)
        assert "API error" in result
        assert "Status: 429" in result

    def test_exception_with_message_attribute(self):
        """Exception with message attribute should use it."""
        error = Exception()
        error.message = "Custom message"
        result = format_anthropic_error(error)
        assert "Custom message" in result


class TestChatCompletionParameters:
    """Tests for the ChatCompletionParameters dataclass."""

    def test_default_values(self):
        """Default values should be set correctly."""
        params = ChatCompletionParameters(model="claude-sonnet-4")
        assert params.model == "claude-sonnet-4"
        assert params.system is None
        assert params.temperature is None
        assert params.effort is None
        assert params.max_tokens == 16384
        assert params.paused is False
        assert params.tools == []
        assert params.mcp_preset_names == []
        assert params.advisor_model is None
        assert params.tool_choice is None

    def test_tools_isolation_between_instances(self):
        """Tools list should not be shared between instances."""
        params1 = ChatCompletionParameters(model="claude-sonnet-4")
        params2 = ChatCompletionParameters(model="claude-sonnet-4")
        params1.tools.append("web_search")
        assert params2.tools == []

    def test_mcp_preset_names_isolation_between_instances(self):
        params1 = ChatCompletionParameters(model="claude-sonnet-4")
        params2 = ChatCompletionParameters(model="claude-sonnet-4")
        params1.mcp_preset_names.append("github")
        assert params2.mcp_preset_names == []


class TestConversation:
    """Tests for the Conversation dataclass."""

    def test_conversation_creation(self):
        """Conversation should store params and messages."""
        params = ChatCompletionParameters(model="claude-sonnet-4")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        conv = Conversation(params=params, messages=messages)

        assert conv.params == params
        assert conv.messages == messages
        assert len(conv.messages) == 2


class TestCalculateCost:
    """Tests for the calculate_cost function."""

    def test_basic_cost(self):
        """Basic cost calculation with input and output tokens."""
        # claude-sonnet-4-6: $3/MTok input, $15/MTok output
        cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == 18.0  # $3 + $15

    def test_zero_tokens(self):
        """Zero tokens should return zero cost."""
        cost = calculate_cost("claude-sonnet-4-6", 0, 0)
        assert cost == 0.0

    def test_cache_write_tokens(self):
        """Cache write tokens cost 2x base input price (1h TTL)."""
        # claude-sonnet-4-6: $3/MTok input, so cache write = $6/MTok
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, cache_creation_tokens=1_000_000)
        assert cost == 6.0

    def test_cache_read_tokens(self):
        """Cache read tokens cost 0.1x base input price."""
        # claude-sonnet-4-6: $3/MTok input, so cache read = $0.30/MTok
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, cache_read_tokens=1_000_000)
        assert cost == pytest.approx(0.30)

    def test_all_token_types(self):
        """Cost with all token types combined."""
        cost = calculate_cost(
            "claude-sonnet-4-6",
            input_tokens=500_000,  # $1.50
            output_tokens=100_000,  # $1.50
            cache_creation_tokens=200_000,  # $1.20
            cache_read_tokens=1_000_000,  # $0.30
        )
        assert cost == pytest.approx(4.50)

    def test_opus_4_6_pricing(self):
        """Opus 4.6 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-4-6", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_opus_4_7_pricing(self):
        """Opus 4.7 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-4-7", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_mythos_preview_pricing(self):
        """Mythos Preview uses $25/MTok input, $125/MTok output."""
        cost = calculate_cost("claude-mythos-preview", 1_000_000, 1_000_000)
        assert cost == 150.0  # $25 + $125

    def test_opus_4_5_pricing(self):
        """Opus 4.5 uses $5/MTok input, $25/MTok output."""
        cost = calculate_cost("claude-opus-4-5", 1_000_000, 1_000_000)
        assert cost == 30.0  # $5 + $25

    def test_opus_4_1_pricing(self):
        """Opus 4.1 uses $15/MTok input, $75/MTok output."""
        cost = calculate_cost("claude-opus-4-1", 1_000_000, 1_000_000)
        assert cost == 90.0  # $15 + $75

    def test_haiku_4_5_pricing(self):
        """Haiku 4.5 uses $1/MTok input, $5/MTok output."""
        cost = calculate_cost("claude-haiku-4-5", 1_000_000, 1_000_000)
        assert cost == 6.0  # $1 + $5

    def test_web_search_cost(self):
        """Web search requests cost $0.01 each."""
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, web_search_requests=1)
        assert cost == pytest.approx(0.01)

    def test_web_search_cost_multiple(self):
        """Multiple web search requests accumulate."""
        cost = calculate_cost("claude-sonnet-4-6", 0, 0, web_search_requests=5)
        assert cost == pytest.approx(0.05)

    def test_web_search_with_tokens(self):
        """Web search cost combines with token costs."""
        cost = calculate_cost(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,  # $3.00
            output_tokens=100_000,  # $1.50
            web_search_requests=3,  # $0.03
        )
        assert cost == pytest.approx(4.53)

    def test_unknown_model_uses_default(self):
        """Unknown model should use default pricing."""
        cost = calculate_cost("unknown-model", 1_000_000, 0)
        assert cost == 15.0  # Default input price

    def test_opus_4_7_context_window(self):
        """Opus 4.7 uses the 1M token context window."""
        assert MODEL_CONTEXT_WINDOWS["claude-opus-4-7"] == 1_000_000


class TestUsageTotals:
    """Tests for the UsageTotals dataclass."""

    def test_accumulate_basic(self):
        """Basic token accumulation from a usage object."""
        totals = UsageTotals()
        usage = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=20,
            server_tool_use=None,
        )
        totals.accumulate(usage)
        assert totals.input_tokens == 100
        assert totals.output_tokens == 50
        assert totals.cache_creation_tokens == 10
        assert totals.cache_read_tokens == 20

    def test_accumulate_multiple(self):
        """Multiple accumulations add up."""
        totals = UsageTotals()
        usage1 = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
        )
        usage2 = MagicMock(
            input_tokens=200,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=None,
        )
        totals.accumulate(usage1)
        totals.accumulate(usage2)
        assert totals.input_tokens == 300
        assert totals.output_tokens == 150

    def test_accumulate_none_is_noop(self):
        """Accumulating None usage should not change totals."""
        totals = UsageTotals()
        totals.accumulate(None)
        assert totals.input_tokens == 0

    def test_accumulate_server_tool_use(self):
        """Server tool use counts are accumulated."""
        totals = UsageTotals()
        server_tool_use = MagicMock(
            web_search_requests=2,
            web_fetch_requests=1,
            code_execution_requests=0,
        )
        usage = MagicMock(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=server_tool_use,
        )
        totals.accumulate(usage)
        assert totals.web_search_requests == 2
        assert totals.web_fetch_requests == 1
        assert totals.code_execution_requests == 0

    def test_accumulate_advisor_iterations(self):
        """Advisor iterations are billed separately from executor iterations."""
        totals = UsageTotals()
        usage = MagicMock(
            iterations=[
                MagicMock(
                    type="message",
                    input_tokens=120,
                    output_tokens=40,
                    cache_creation_input_tokens=0,
                    cache_read_input_tokens=10,
                ),
                MagicMock(
                    type="advisor_message",
                    input_tokens=300,
                    output_tokens=700,
                    cache_creation_input_tokens=50,
                    cache_read_input_tokens=25,
                ),
                MagicMock(
                    type="message",
                    input_tokens=80,
                    output_tokens=60,
                    cache_creation_input_tokens=5,
                    cache_read_input_tokens=0,
                ),
            ],
            server_tool_use=None,
        )

        totals.accumulate(usage)

        assert totals.input_tokens == 200
        assert totals.output_tokens == 100
        assert totals.cache_creation_tokens == 5
        assert totals.cache_read_tokens == 10
        assert totals.advisor_calls == 1
        assert totals.advisor_input_tokens == 300
        assert totals.advisor_output_tokens == 700
        assert totals.advisor_cache_creation_tokens == 50
        assert totals.advisor_cache_read_tokens == 25

    def test_apply_to_sets_all_fields(self):
        """apply_to stamps all fields onto a target object."""
        totals = UsageTotals(
            input_tokens=100,
            output_tokens=50,
            cache_creation_tokens=10,
            cache_read_tokens=20,
            web_search_requests=1,
            web_fetch_requests=2,
            code_execution_requests=3,
            context_compacted=True,
        )
        target = MagicMock()
        totals.apply_to(target, context_window=200_000)
        assert target.input_tokens == 100
        assert target.output_tokens == 50
        assert target.context_compacted is True
        assert target.context_warning is False  # 100 < 200_000 * 0.85
        assert target.advisor_calls == 0

    def test_apply_to_context_warning(self):
        """context_warning is True when input tokens exceed 85% of window."""
        totals = UsageTotals(input_tokens=175_000)
        target = MagicMock()
        totals.apply_to(target, context_window=200_000)
        assert target.context_warning is True


class TestAvailableEmbedSpace:
    """Tests for the available_embed_space helper."""

    def test_empty_embeds(self):
        """No embeds should return full limit."""
        assert available_embed_space([]) == DISCORD_EMBED_TOTAL_LIMIT

    def test_with_reserve(self):
        """Reserve should be subtracted."""
        assert available_embed_space([], reserve=500) == DISCORD_EMBED_TOTAL_LIMIT - 500

    def test_with_existing_embeds(self):
        """Existing embed content reduces available space."""
        embed = MagicMock()
        embed.description = "a" * 1000
        embed.title = "Title"
        space = available_embed_space([embed])
        assert space == DISCORD_EMBED_TOTAL_LIMIT - 1005
