from dataclasses import dataclass, field
from typing import Any

from discord import Member, User

CHUNK_TEXT_SIZE = 3500  # Maximum number of characters in each text chunk.

# Claude models
CLAUDE_MODELS = [
    "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250514",
    "claude-sonnet-4-20250514",
    "claude-haiku-3-5-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
]


@dataclass
class ChatCompletionParameters:
    """A dataclass to store the parameters for a chat completion."""

    model: str
    system: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int = 4096
    conversation_starter: Member | User | None = None
    conversation_id: int | None = None
    channel_id: int | None = None
    paused: bool | None = False
    messages: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API calls."""
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": self.messages,
        }
        if self.system:
            payload["system"] = self.system
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.top_k is not None:
            payload["top_k"] = self.top_k
        return payload


@dataclass
class Conversation:
    """A dataclass to store conversation state."""

    params: ChatCompletionParameters
    messages: list[dict[str, Any]]


def chunk_text(text: str, chunk_size: int = CHUNK_TEXT_SIZE) -> list[str]:
    """
    Splits a string into chunks of a specified size.

    Args:
        text: The string to split.
        chunk_size: The maximum size of each chunk.

    Returns:
        A list of strings, where each string is a chunk of the original text.
    """
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def truncate_text(text: str | None, max_length: int, suffix: str = "...") -> str | None:
    """
    Truncate text to max_length, adding suffix if truncated.

    Args:
        text: The text to truncate
        max_length: Maximum length before truncation
        suffix: String to append when truncated (default "...")

    Returns:
        Original text if under max_length, otherwise truncated with suffix
    """
    if text is None:
        return None
    if len(text) <= max_length:
        return text
    return text[:max_length] + suffix


def format_anthropic_error(error: Exception) -> str:
    """Return a readable description for exceptions raised by Anthropic operations."""
    message = getattr(error, "message", None)
    if not isinstance(message, str) or not message.strip():
        message = str(error).strip()

    status = getattr(error, "status_code", None)
    error_type = type(error).__name__

    details = []
    if status is not None:
        details.append(f"Status: {status}")
    if error_type and error_type != "Exception":
        details.append(f"Error: {error_type}")

    if details:
        return f"{message}\n\n" + "\n".join(details)
    return message
