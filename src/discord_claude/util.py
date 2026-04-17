from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Protocol, TypedDict

from discord import Embed, Member, User

from discord_claude.config.pricing import (  # noqa: F401 — re-exported for callers
    MODEL_CONTEXT_WINDOWS,
    MODEL_PRICING,
    UNKNOWN_MODEL_PRICING,
    WEB_SEARCH_COST_PER_REQUEST,
)

CHUNK_TEXT_SIZE = 3500  # Maximum number of characters in each text chunk.

CACHE_TTL = "1h"  # 1-hour TTL for prompt caching (2x base input price for writes)

ADVISOR_BETA = "advisor-tool-2026-03-01"
ADVISOR_TOOL_TYPE = "advisor_20260301"
ADVISOR_TOOL_NAME = "advisor"
ADVISOR_MAX_USES = 3
ADVISOR_MODEL_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "claude-haiku-4-5": ("claude-opus-4-6",),
    "claude-sonnet-4-6": ("claude-opus-4-6",),
    "claude-opus-4-6": ("claude-opus-4-6",),
}

# Models that support adaptive thinking
ADAPTIVE_THINKING_MODELS = {"claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6"}

# Models that reject explicit sampling parameter overrides.
SAMPLING_LOCKED_MODELS = {"claude-opus-4-7"}

# Models that only support adaptive thinking (no budget_tokens mode).
ADAPTIVE_ONLY_THINKING_MODELS = {"claude-opus-4-7"}

# Models that support server-side compaction (beta)
COMPACTION_MODELS = {"claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6"}

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
    input_price, output_price = MODEL_PRICING.get(model, UNKNOWN_MODEL_PRICING)
    return (
        (input_tokens / 1_000_000) * input_price
        + (output_tokens / 1_000_000) * output_price
        + (cache_creation_tokens / 1_000_000) * input_price * 2.0
        + (cache_read_tokens / 1_000_000) * input_price * 0.10
        + web_search_requests * WEB_SEARCH_COST_PER_REQUEST
    )


def get_default_advisor_model(executor_model: str) -> str | None:
    """Return the default compatible advisor model for an executor model."""
    compatible_models = ADVISOR_MODEL_COMPATIBILITY.get(executor_model)
    if not compatible_models:
        return None
    return compatible_models[0]


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
    advisor_calls: int = 0
    advisor_input_tokens: int = 0
    advisor_output_tokens: int = 0
    advisor_cache_creation_tokens: int = 0
    advisor_cache_read_tokens: int = 0
    context_compacted: bool = False

    def _accumulate_executor_usage(self, usage: Any) -> None:
        """Add usage billed at the executor model's rates."""
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    def _accumulate_advisor_usage(self, usage: Any) -> None:
        """Add usage billed at the advisor model's rates."""
        self.advisor_calls += 1
        self.advisor_input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.advisor_output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.advisor_cache_creation_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.advisor_cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

    def accumulate(self, usage: Any) -> None:
        """Add a single API response's usage to running totals."""
        if usage is None:
            return

        iterations = getattr(usage, "iterations", None)
        if isinstance(iterations, (list, tuple)):
            for iteration in iterations:
                iteration_type = getattr(iteration, "type", None)
                if iteration_type == "advisor_message":
                    self._accumulate_advisor_usage(iteration)
                elif iteration_type == "message":
                    self._accumulate_executor_usage(iteration)
        else:
            self._accumulate_executor_usage(usage)

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
        parsed.advisor_calls = self.advisor_calls
        parsed.advisor_input_tokens = self.advisor_input_tokens
        parsed.advisor_output_tokens = self.advisor_output_tokens
        parsed.advisor_cache_creation_tokens = self.advisor_cache_creation_tokens
        parsed.advisor_cache_read_tokens = self.advisor_cache_read_tokens
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
    mcp_preset_names: list[str] = field(default_factory=list)
    advisor_model: str | None = None
    tool_choice: ToolChoice | None = None


# Conversation key: (user_id, channel_id) for O(1) lookup
ConversationKey = tuple[int, int]


@dataclass
class Conversation:
    """A dataclass to store conversation state."""

    params: ChatCompletionParameters
    messages: list[dict[str, Any]]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


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
    api_error_type = getattr(error, "error_type", None)
    error_type = api_error_type or type(error).__name__

    details = []
    if status is not None:
        details.append(f"Status: {status}")
    if error_type and error_type != "Exception":
        details.append(f"Error: {error_type}")

    if details:
        return f"{message}\n\n" + "\n".join(details)
    return message
