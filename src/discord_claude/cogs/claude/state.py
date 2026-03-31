from datetime import date
from typing import Any

from discord import Member, User

from discord_claude.util import COMPACTION_SUMMARY_MODEL, ConversationKey, calculate_cost

from .responses import ParsedResponse
from .views import ButtonView


async def compact_conversation(
    cog,
    messages: list[dict[str, Any]],
    system: str | None = None,
) -> str:
    """Compact conversation history into a summary for non-compaction models."""
    summary_prompt = (
        "You are summarizing a conversation to allow it to continue in a fresh context window. "
        "Write a concise continuation summary that preserves:\n\n"
        "1. **Task/Topic**: The user's core request or discussion topic\n"
        "2. **Key Context**: Important facts, decisions, and constraints established\n"
        "3. **Current State**: What has been discussed/completed so far\n"
        "4. **Next Steps**: What the user is likely to ask about next\n\n"
        "Be concise but complete — preserve information that prevents repeated work. "
        "Wrap your summary in <summary></summary> tags."
    )

    summary_messages = list(messages) + [{"role": "user", "content": summary_prompt}]
    create_kwargs: dict[str, Any] = {
        "model": COMPACTION_SUMMARY_MODEL,
        "max_tokens": 4096,
        "messages": summary_messages,
    }
    if system:
        create_kwargs["system"] = system

    summary_response = await cog.client.messages.create(**create_kwargs)
    summary_text = "".join(block.text for block in summary_response.content if block.type == "text")

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


def track_daily_cost(
    cog,
    user_id: int,
    model: str,
    parsed: ParsedResponse,
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
    key = (user_id, date.today().isoformat())
    cog.daily_costs[key] = cog.daily_costs.get(key, 0.0) + cost

    cog.logger.info(
        "COST | command=chat | user=%s | model=%s"
        " | input=%d | output=%d"
        " | cache_write=%d | cache_read=%d"
        " | web_searches=%d | web_fetches=%d | code_execs=%d"
        " | cost=$%.4f | daily=$%.4f",
        user_id,
        model,
        parsed.input_tokens,
        parsed.output_tokens,
        parsed.cache_creation_tokens,
        parsed.cache_read_tokens,
        parsed.web_search_requests,
        parsed.web_fetch_requests,
        parsed.code_execution_requests,
        cost,
        cog.daily_costs[key],
    )

    return cost, cog.daily_costs[key]


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
    "cleanup_conversation",
    "compact_conversation",
    "create_button_view",
    "stop_conversation",
    "strip_previous_view",
    "track_daily_cost",
]
