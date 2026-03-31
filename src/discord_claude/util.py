from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, TypedDict

from discord import Embed, Member, User

CHUNK_TEXT_SIZE = 3500  # Maximum number of characters in each text chunk.

CACHE_TTL = "1h"  # 1-hour TTL for prompt caching (2x base input price for writes)

# Models that support adaptive thinking
ADAPTIVE_THINKING_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

# Models that support server-side compaction (beta)
COMPACTION_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6"}

# Context window sizes per model (input tokens)
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-opus-4-1": 200_000,
    "claude-haiku-4-5": 200_000,
}

# Context management thresholds
CONTEXT_WARNING_THRESHOLD = 0.85  # Show warning embed at 85% of context window
CONTEXT_COMPACTION_THRESHOLD = 0.75  # Trigger manual compaction at 75% (non-compaction models)
COMPACTION_SUMMARY_MODEL = "claude-haiku-4-5"  # Cheap model for generating summaries

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
        "type": "web_fetch_20260309",
        "name": "web_fetch",
        "max_uses": 5,
        "use_cache": False,
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
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Server tool pricing
WEB_SEARCH_COST_PER_REQUEST = 0.01  # $10 per 1,000 searches

# Discord embed limits
DISCORD_EMBED_TOTAL_LIMIT = 6000  # Max chars across all embeds in a single message
CITATION_EMBED_RESERVE = 500  # Chars reserved for a potential citations embed


def available_embed_space(embeds: list[Embed], reserve: int = 0) -> int:
    """Calculate remaining character budget across all embeds in a message."""
    used = sum(len(e.description or "") + len(e.title or "") for e in embeds)
    return DISCORD_EMBED_TOTAL_LIMIT - used - reserve


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    web_search_requests: int = 0,
) -> float:
    """Calculate the cost in dollars for a given model and token usage.

    Cache write tokens cost 2x base input price (1h TTL); cache read tokens cost 0.1x.
    Web search requests cost $0.01 each ($10 per 1,000 searches).
    """
    input_price, output_price = MODEL_PRICING.get(model, (15.0, 75.0))
    return (
        (input_tokens / 1_000_000) * input_price
        + (output_tokens / 1_000_000) * output_price
        + (cache_creation_tokens / 1_000_000) * input_price * 2.0
        + (cache_read_tokens / 1_000_000) * input_price * 0.10
        + web_search_requests * WEB_SEARCH_COST_PER_REQUEST
    )


@dataclass
class UsageTotals:
    """Accumulates token/tool usage across multiple API iterations."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    web_search_requests: int = 0
    web_fetch_requests: int = 0
    code_execution_requests: int = 0
    context_compacted: bool = False

    def accumulate(self, usage: Any) -> None:
        """Add a single API response's usage to running totals."""
        if usage is None:
            return
        self.input_tokens += getattr(usage, "input_tokens", 0)
        self.output_tokens += getattr(usage, "output_tokens", 0)
        self.cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        server_tool_use = getattr(usage, "server_tool_use", None)
        if server_tool_use:
            self.web_search_requests += getattr(server_tool_use, "web_search_requests", 0) or 0
            self.web_fetch_requests += getattr(server_tool_use, "web_fetch_requests", 0) or 0
            self.code_execution_requests += (
                getattr(server_tool_use, "code_execution_requests", 0) or 0
            )

    def apply_to(self, parsed: Any, context_window: int) -> None:
        """Stamp all accumulated totals onto a ParsedResponse."""
        parsed.input_tokens = self.input_tokens
        parsed.output_tokens = self.output_tokens
        parsed.cache_creation_tokens = self.cache_creation_tokens
        parsed.cache_read_tokens = self.cache_read_tokens
        parsed.web_search_requests = self.web_search_requests
        parsed.web_fetch_requests = self.web_fetch_requests
        parsed.code_execution_requests = self.code_execution_requests
        parsed.context_compacted = self.context_compacted
        parsed.context_warning = self.input_tokens > context_window * CONTEXT_WARNING_THRESHOLD


class ToolChoiceAuto(TypedDict):
    """Allow Claude to decide whether to use available tools."""

    type: Literal["auto"]


class ToolChoiceAny(TypedDict):
    """Require Claude to use one of the available tools."""

    type: Literal["any"]


class ToolChoiceNone(TypedDict):
    """Disable tool invocation while still allowing tool definitions."""

    type: Literal["none"]


class ToolChoiceTool(TypedDict):
    """Force Claude to call a specific available tool."""

    type: Literal["tool"]
    name: str


ToolChoice = ToolChoiceAuto | ToolChoiceAny | ToolChoiceNone | ToolChoiceTool


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
    tools: list[str] = field(default_factory=list)
    tool_choice: ToolChoice | None = None


# Conversation key: (user_id, channel_id) for O(1) lookup
ConversationKey = tuple[int, int]


@dataclass
class Conversation:
    """A dataclass to store conversation state."""

    params: ChatCompletionParameters
    messages: list[dict[str, Any]]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ToolHandler(Protocol):
    """Protocol for client-side tool handlers."""

    async def execute(self, tool_input: dict[str, Any], user_id: int) -> str: ...


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
