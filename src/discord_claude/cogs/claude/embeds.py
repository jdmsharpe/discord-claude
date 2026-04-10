import re

from discord import Colour, Embed

from discord_claude.util import CITATION_EMBED_RESERVE, available_embed_space, chunk_text

from .responses import ParsedResponse


def append_thinking_embeds(embeds: list[Embed], thinking_text: str) -> None:
    """Append thinking text as a spoilered Discord embed."""
    if not thinking_text:
        return

    if len(thinking_text) > 3500:
        thinking_text = thinking_text[:3450] + "\n\n... [thinking truncated]"

    embeds.append(
        Embed(
            title="Thinking",
            description=f"||{thinking_text}||",
            color=Colour.light_grey(),
        )
    )


def append_response_embeds(embeds: list[Embed], response_text: str) -> None:
    """Append response text as Discord embeds, handling chunking for long responses."""
    available = available_embed_space(embeds, reserve=CITATION_EMBED_RESERVE)
    if available < 50:
        return

    if len(response_text) > available:
        response_text = (
            response_text[: available - 40] + "\n\n... [Response truncated due to length]"
        )

    response_text = re.sub(r"\n{3,}", "\n\n", response_text)

    for index, chunk in enumerate(chunk_text(response_text, 3500), start=1):
        embeds.append(
            Embed(
                title="Response" + (f" (Part {index})" if index > 1 else ""),
                description=chunk,
                color=Colour.orange(),
            )
        )


def append_citations_embed(embeds: list[Embed], citations: list[dict[str, str]]) -> None:
    """Append a Sources embed listing web search links and/or document citations."""
    if not citations:
        return

    web_lines = []
    doc_lines = []

    for citation in citations:
        kind = citation.get("kind", "web")
        if kind == "web":
            title = citation.get("title", citation.get("url", ""))
            url = citation.get("url", "")
            if url:
                web_lines.append(f"[{title}]({url})")
        elif kind == "document":
            cited_text = citation.get("cited_text", "")
            doc_title = citation.get("document_title", "")
            location = citation.get("location", "")
            if cited_text:
                if len(cited_text) > 150:
                    cited_text = cited_text[:147] + "..."
                source = doc_title
                if location:
                    source += f", {location}"
                doc_lines.append(f"> {cited_text}\n> — *{source}*")

    parts = []
    if web_lines:
        numbered = [f"{index}. {line}" for index, line in enumerate(web_lines[:20], 1)]
        parts.append("\n".join(numbered))
    if doc_lines:
        parts.append("\n\n".join(doc_lines[:10]))

    if not parts:
        return

    description = "\n\n".join(parts)
    remaining_chars = available_embed_space(embeds, reserve=len("Sources"))
    if remaining_chars < 50:
        return

    max_description_length = min(4000, remaining_chars)
    if len(description) > max_description_length:
        description = description[: max_description_length - 3] + "..."

    embeds.append(
        Embed(
            title="Sources",
            description=description,
            color=Colour.orange(),
        )
    )


def append_stop_reason_embed(
    embeds: list[Embed],
    stop_reason: str,
    stop_details: dict[str, str | None] | None = None,
) -> None:
    """Append a warning embed for non-standard stop reasons."""
    if stop_reason == "max_tokens":
        embeds.append(
            Embed(
                title="Response Truncated",
                description="The response reached the maximum token limit and was cut short.",
                color=Colour.yellow(),
            )
        )
    elif stop_reason == "model_context_window_exceeded":
        embeds.append(
            Embed(
                title="Context Limit Reached",
                description="This conversation has exceeded the model's context window. Please start a new conversation.",
                color=Colour.yellow(),
            )
        )
    elif stop_reason == "refusal":
        description = "Claude was unable to fulfill this request."
        if stop_details:
            details_lines = []
            category = stop_details.get("category")
            explanation = stop_details.get("explanation")
            if category:
                details_lines.append(f"Category: `{category}`")
            if explanation:
                details_lines.append(f"Explanation: {explanation}")
            if details_lines:
                description += "\n\n" + "\n".join(details_lines)
        embeds.append(
            Embed(
                title="Request Declined",
                description=description,
                color=Colour.yellow(),
            )
        )


def append_context_warning_embed(embeds: list[Embed]) -> None:
    """Append a warning embed when context usage exceeds 85% of the window."""
    embeds.append(
        Embed(
            title="Context Window Warning",
            description=(
                "This conversation is using over 85% of the model's context window. "
                "Consider starting a new conversation soon to avoid degraded responses."
            ),
            color=Colour.yellow(),
        )
    )


def append_compaction_embed(embeds: list[Embed]) -> None:
    """Append an info embed when context was automatically compacted."""
    embeds.append(
        Embed(
            title="Context Compacted",
            description=(
                "This conversation's history was automatically summarized to stay "
                "within the model's context window. Earlier details may be condensed."
            ),
            color=Colour.blue(),
        )
    )


def append_pricing_embed(
    embeds: list[Embed],
    parsed: ParsedResponse,
    request_cost: float,
    daily_cost: float,
) -> None:
    """Append a compact pricing embed showing cost and token usage."""
    parts = [
        f"${request_cost:.4f} · {parsed.input_tokens:,} tokens in / {parsed.output_tokens:,} tokens out"
    ]
    if parsed.cache_read_tokens:
        parts.append(f"{parsed.cache_read_tokens:,} cached")
    if parsed.advisor_calls:
        parts.append(
            f"advisor {parsed.advisor_calls} call{'s' if parsed.advisor_calls != 1 else ''}"
        )
    if parsed.web_search_requests:
        parts.append(
            f"{parsed.web_search_requests} search{'es' if parsed.web_search_requests != 1 else ''}"
        )
    if parsed.web_fetch_requests:
        parts.append(
            f"{parsed.web_fetch_requests} fetch{'es' if parsed.web_fetch_requests != 1 else ''}"
        )
    if parsed.code_execution_requests:
        parts.append(
            f"{parsed.code_execution_requests} code exec{'s' if parsed.code_execution_requests != 1 else ''}"
        )
    parts.append(f"daily ${daily_cost:.2f}")
    embeds.append(Embed(description=" · ".join(parts), color=Colour.orange()))


__all__ = [
    "append_citations_embed",
    "append_compaction_embed",
    "append_context_warning_embed",
    "append_pricing_embed",
    "append_response_embeds",
    "append_stop_reason_embed",
    "append_thinking_embeds",
]
