import pytest

from src.util import (
    CHUNK_TEXT_SIZE,
    ChatCompletionParameters,
    Conversation,
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
        setattr(error, "status_code", 429)
        result = format_anthropic_error(error)
        assert "API error" in result
        assert "Status: 429" in result

    def test_exception_with_message_attribute(self):
        """Exception with message attribute should use it."""
        error = Exception()
        setattr(error, "message", "Custom message")
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
        assert params.messages == []
        assert params.tools == []

    def test_to_dict_minimal(self):
        """to_dict with minimal params should include required fields."""
        params = ChatCompletionParameters(model="claude-sonnet-4")
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert result["model"] == "claude-sonnet-4"
        assert result["max_tokens"] == 16384
        assert result["messages"] == [{"role": "user", "content": "Hello"}]
        assert "system" not in result
        assert "temperature" not in result
        assert "tools" not in result

    def test_to_dict_with_optional_params(self):
        """to_dict with optional params should include them."""
        params = ChatCompletionParameters(
            model="claude-sonnet-4",
            system="You are helpful.",
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_tokens=2048,
        )
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert result["system"] == "You are helpful."
        assert result["temperature"] == 0.7
        assert result["top_p"] == 0.9
        assert result["top_k"] == 40
        assert result["max_tokens"] == 2048


    def test_to_dict_with_effort(self):
        """to_dict with effort should include it."""
        params = ChatCompletionParameters(
            model="claude-sonnet-4-6",
            effort="high",
        )
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert result["effort"] == "high"

    def test_to_dict_without_effort(self):
        """to_dict without effort should not include it."""
        params = ChatCompletionParameters(model="claude-sonnet-4")
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert "effort" not in result

    def test_to_dict_with_tools(self):
        """to_dict with tools should include tool definitions."""
        params = ChatCompletionParameters(
            model="claude-sonnet-4",
            tools=["web_search", "memory"],
        )
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert "tools" in result
        assert len(result["tools"]) == 2
        assert result["tools"][0]["type"] == "web_search_20260209"
        assert result["tools"][1]["type"] == "memory_20250818"

    def test_to_dict_ignores_invalid_tools(self):
        """to_dict ignores tool keys not in AVAILABLE_TOOLS."""
        params = ChatCompletionParameters(
            model="claude-sonnet-4",
            tools=["web_search", "nonexistent_tool"],
        )
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert len(result["tools"]) == 1
        assert result["tools"][0]["name"] == "web_search"

    def test_tools_isolation_between_instances(self):
        """Tools list should not be shared between instances."""
        params1 = ChatCompletionParameters(model="claude-sonnet-4")
        params2 = ChatCompletionParameters(model="claude-sonnet-4")
        params1.tools.append("web_search")
        assert params2.tools == []


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
            input_tokens=500_000,       # $1.50
            output_tokens=100_000,      # $1.50
            cache_creation_tokens=200_000,  # $1.20
            cache_read_tokens=1_000_000,    # $0.30
        )
        assert cost == pytest.approx(4.50)

    def test_unknown_model_uses_default(self):
        """Unknown model should use default pricing."""
        cost = calculate_cost("unknown-model", 1_000_000, 0)
        assert cost == 15.0  # Default input price
