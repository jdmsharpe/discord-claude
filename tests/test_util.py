from src.util import (
    CHUNK_TEXT_SIZE,
    ChatCompletionParameters,
    Conversation,
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
        params = ChatCompletionParameters(model="claude-sonnet-4-20250514")
        assert params.model == "claude-sonnet-4-20250514"
        assert params.system is None
        assert params.temperature is None
        assert params.max_tokens == 4096
        assert params.paused is False
        assert params.messages == []

    def test_to_dict_minimal(self):
        """to_dict with minimal params should include required fields."""
        params = ChatCompletionParameters(model="claude-sonnet-4-20250514")
        params.messages = [{"role": "user", "content": "Hello"}]
        result = params.to_dict()

        assert result["model"] == "claude-sonnet-4-20250514"
        assert result["max_tokens"] == 4096
        assert result["messages"] == [{"role": "user", "content": "Hello"}]
        assert "system" not in result
        assert "temperature" not in result

    def test_to_dict_with_optional_params(self):
        """to_dict with optional params should include them."""
        params = ChatCompletionParameters(
            model="claude-sonnet-4-20250514",
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


class TestConversation:
    """Tests for the Conversation dataclass."""

    def test_conversation_creation(self):
        """Conversation should store params and messages."""
        params = ChatCompletionParameters(model="claude-sonnet-4-20250514")
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        conv = Conversation(params=params, messages=messages)

        assert conv.params == params
        assert conv.messages == messages
        assert len(conv.messages) == 2
