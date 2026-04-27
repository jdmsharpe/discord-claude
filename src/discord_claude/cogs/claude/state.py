import contextlib
from datetime import date, datetime, timedelta, timezone
from typing import Any

from discord import Member, User
from pydantic import BaseModel, Field

from discord_claude.util import (
    ADVISOR_TOOL_NAME,
    COMPACTION_SUMMARY_MODEL,
    ConversationKey,
    calculate_cost,
)

from .responses import ParsedResponse
from .views import ButtonView


class ConversationSummary(BaseModel):
    """Structured continuation summary for a fresh context window.

    Each field is required, so the compaction call cannot drop a section.
    """

    task: str = Field(description="The user's core request or discussion topic.")
    key_context: str = Field(
        description="Important facts, decisions, and constraints established so far."
    )
    current_state: str = Field(description="What has been discussed or completed so far.")
    next_steps: str = Field(description="What the user is likely to ask about next.")

    def to_message_text(self) -> str:
        """Render the summary as a single user-message body."""
        return (
            "<summary>\n"
            f"**Task/Topic**: {self.task}\n\n"
            f"**Key Context**: {self.key_context}\n\n"
            f"**Current State**: {self.current_state}\n\n"
            f"**Next Steps**: {self.next_steps}\n"
            "</summary>"
        )


MAX_ACTIVE_CONVERSATIONS = 100
CONVERSATION_TTL = timedelta(hours=12)
DAILY_COST_RETENTION_DAYS = 30


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _extract_daily_total(value: float | tuple[float, datetime]) -> float:
    return value[0] if isinstance(value, tuple) else value


def _copy_messages_without_advisor_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clone message history while removing advisor-only transcript blocks.

    Anthropic requires the advisor tool definition to be present when replaying
    `advisor_tool_result` blocks. Manual compaction replays history without tools,
    so we strip those blocks for the summarization pass.
    """
    sanitized_messages: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            sanitized_messages.append(dict(message))
            continue

        filtered_content = []
        for block in content:
            block_type = getattr(block, "type", None)
            block_name = getattr(block, "name", None)
            if isinstance(block, dict):
                block_type = block.get("type")
                block_name = block.get("name")
            if block_type == "advisor_tool_result":
                continue
            if block_type == "server_tool_use" and block_name == ADVISOR_TOOL_NAME:
                continue
            filtered_content.append(block)

        sanitized_message = dict(message)
        sanitized_message["content"] = filtered_content
        sanitized_messages.append(sanitized_message)

    return sanitized_messages


async def compact_conversation(
    cog,
    messages: list[dict[str, Any]],
    system: str | None = None,
) -> str:
    """Compact conversation history into a structured summary for non-compaction models."""
    summary_prompt = (
        "Summarize this conversation so it can continue in a fresh context window. "
        "Populate every section: capture the task, the established context and decisions, "
        "what has been completed so far, and the likely next user question. "
        "Be concise but complete — preserve information that prevents repeated work."
    )

    summary_messages = _copy_messages_without_advisor_blocks(messages) + [
        {"role": "user", "content": summary_prompt}
    ]
    parse_kwargs: dict[str, Any] = {
        "model": COMPACTION_SUMMARY_MODEL,
        "max_tokens": 4096,
        "messages": summary_messages,
        "output_format": ConversationSummary,
    }
    if system:
        parse_kwargs["system"] = system

    summary_response = await cog.client.messages.parse(**parse_kwargs)
    summary_text = summary_response.parsed_output.to_message_text()

    messages.clear()
    messages.append({"role": "user", "content": summary_text})

    cog.logger.info(
        "Context compacted: conversation reduced to summary (%d chars)",
        len(summary_text),
    )
    return summary_text


async def strip_previous_view(cog, user: Member | User) -> None:
    """Edit the last message that had buttons to remove its view."""
    prev = cog.last_view_messages.pop(user, None)
    if prev is not None:
        try:
            await prev.edit(view=None)
        except Exception as error:
            cog.logger.debug("Failed to strip previous view: %s", error)


async def cleanup_conversation(cog, user: Member | User) -> None:
    """Remove button view from the last message and clean up view state."""
    await strip_previous_view(cog, user)
    cog.views.pop(user, None)


async def stop_conversation(cog, conversation_key: ConversationKey, user: Member | User) -> None:
    """Stop a conversation and clean up resources."""
    cog.conversations.pop(conversation_key, None)
    await cleanup_conversation(cog, user)
    await prune_runtime_state(cog)


async def prune_runtime_state(cog) -> None:
    """Evict stale conversations, cascade-clean views, and prune old daily costs."""
    now = _now_utc()

    stale_keys = [
        key
        for key, conversation in cog.conversations.items()
        if now - conversation.updated_at > CONVERSATION_TTL
    ]

    active = [
        (key, conversation)
        for key, conversation in cog.conversations.items()
        if key not in stale_keys
    ]
    overflow = len(active) - MAX_ACTIVE_CONVERSATIONS
    if overflow > 0:
        active.sort(key=lambda item: item[1].updated_at)
        stale_keys.extend(key for key, _ in active[:overflow])

    for key in dict.fromkeys(stale_keys):
        conversation = cog.conversations.pop(key, None)
        if conversation is None:
            continue
        starter = conversation.params.conversation_starter
        if starter is not None:
            with contextlib.suppress(Exception):
                await cleanup_conversation(cog, starter)

    prune_daily_costs(cog)


def prune_daily_costs(cog) -> None:
    cutoff = date.today() - timedelta(days=DAILY_COST_RETENTION_DAYS)
    expired_keys = [key for key in cog.daily_costs if date.fromisoformat(key[1]) < cutoff]
    for key in expired_keys:
        cog.daily_costs.pop(key, None)


def track_daily_cost(
    cog,
    user_id: int,
    model: str,
    parsed: ParsedResponse,
    advisor_model: str | None = None,
) -> tuple[float, float]:
    """Add this request's cost to the user's daily total and return request and daily totals."""
    cost = calculate_cost(
        model,
        parsed.input_tokens,
        parsed.output_tokens,
        parsed.cache_creation_tokens,
        parsed.cache_read_tokens,
        parsed.web_search_requests,
    )
    if advisor_model and parsed.advisor_calls:
        cost += calculate_cost(
            advisor_model,
            parsed.advisor_input_tokens,
            parsed.advisor_output_tokens,
            parsed.advisor_cache_creation_tokens,
            parsed.advisor_cache_read_tokens,
        )
    prune_daily_costs(cog)
    key = (user_id, date.today().isoformat())
    current_total = _extract_daily_total(cog.daily_costs.get(key, 0.0))
    new_total = current_total + cost
    cog.daily_costs[key] = (new_total, _now_utc())

    cog.logger.info(
        "COST | command=chat | user=%s | model=%s"
        " | input=%d | output=%d"
        " | cache_write=%d | cache_read=%d"
        " | advisor=%s | advisor_calls=%d"
        " | advisor_input=%d | advisor_output=%d"
        " | advisor_cache_write=%d | advisor_cache_read=%d"
        " | web_searches=%d | web_fetches=%d | code_execs=%d"
        " | cost=$%.4f | daily=$%.4f",
        user_id,
        model,
        parsed.input_tokens,
        parsed.output_tokens,
        parsed.cache_creation_tokens,
        parsed.cache_read_tokens,
        advisor_model or "none",
        parsed.advisor_calls,
        parsed.advisor_input_tokens,
        parsed.advisor_output_tokens,
        parsed.advisor_cache_creation_tokens,
        parsed.advisor_cache_read_tokens,
        parsed.web_search_requests,
        parsed.web_fetch_requests,
        parsed.code_execution_requests,
        cost,
        new_total,
    )

    return cost, new_total


def create_button_view(
    cog,
    *,
    user,
    conversation_key: ConversationKey,
    initial_tools: list[str] | None,
    initial_tool_choice,
) -> ButtonView:
    """Create the provider-local button view for an active conversation."""
    view = ButtonView(
        conversation_starter=user,
        conversation_key=conversation_key,
        initial_tools=initial_tools,
        initial_tool_choice=initial_tool_choice,
        get_conversation=lambda key: cog.conversations.get(key),
        on_regenerate=cog.handle_new_message_in_conversation,
        on_stop=cog._stop_conversation,
    )
    cog.views[user] = view
    return view


__all__ = [
    "CONVERSATION_TTL",
    "DAILY_COST_RETENTION_DAYS",
    "MAX_ACTIVE_CONVERSATIONS",
    "ConversationSummary",
    "_copy_messages_without_advisor_blocks",
    "cleanup_conversation",
    "compact_conversation",
    "create_button_view",
    "prune_daily_costs",
    "prune_runtime_state",
    "stop_conversation",
    "strip_previous_view",
    "track_daily_cost",
]
