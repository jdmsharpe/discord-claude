from dataclasses import dataclass, field
from typing import Any

from discord import Member, User

CHUNK_TEXT_SIZE = 3500  # Maximum number of characters in each text chunk.

# Models that support adaptive thinking
ADAPTIVE_THINKING_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

# Models that support server-side compaction (beta)
COMPACTION_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

# Models that support manual extended thinking (type: "enabled" with budget_tokens)
EXTENDED_THINKING_MODELS = {
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-1",
    "claude-haiku-4-5",
}

# Tool definitions for the Anthropic API
AVAILABLE_TOOLS: dict[str, dict[str, Any]] = {
    "web_search": {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": 5,
    },
    "web_fetch": {
        "type": "web_fetch_20260209",
        "name": "web_fetch",
        "max_uses": 5,
    },
    "code_execution": {
        "type": "code_execution_20250825",
        "name": "code_execution",
    },
    "memory": {
        "type": "memory_20250818",
        "name": "memory",
    },
}

# Per-million-token pricing: (input_cost, output_cost)
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost in dollars for a given model and token usage."""
    input_price, output_price = MODEL_PRICING.get(model, (15.0, 75.0))
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price


# Claude models
CLAUDE_MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-1",
    "claude-haiku-4-5",
]


@dataclass
class ChatCompletionParameters:
    """A dataclass to store the parameters for a chat completion."""

    model: str
    system: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int = 16384
    conversation_starter: Member | User | None = None
    conversation_id: int | None = None
    channel_id: int | None = None
    effort: str | None = None
    thinking_budget: int | None = None
    paused: bool | None = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

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
        if self.effort is not None:
            payload["effort"] = self.effort
        if self.tools:
            payload["tools"] = [
                AVAILABLE_TOOLS[t] for t in self.tools if t in AVAILABLE_TOOLS
            ]
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
