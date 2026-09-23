import re

from discord import Colour, Embed

from discord_claude.cost_line import count_label, format_cost_line
from discord_claude.util import chunk_text

from .responses import ParsedResponse


def _fit_markdown_sections(
    sections: list[tuple[str | None, list[str]]],
    max_length: int = 4000,
) -> str:
    """Fit complete Markdown entries without slicing through links."""

    rendered_sections: list[str] = []
    for heading, entries in sections:
        accepted: list[str] = []
        for entry in entries:
            body = "\n".join([*accepted, entry])
            rendered = f"{heading}\n{body}" if heading else body
            candidate = "\n\n".join([*rendered_sections, rendered])
            if len(candidate) > max_length:
                break
            accepted.append(entry)
        if accepted:
            body = "\n".join(accepted)
            rendered_sections.append(f"{heading}\n{body}" if heading else body)
    return "\n\n".join(rendered_sections)


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
            # PDF extraction keeps layout line breaks. Discord's `>` quotes one
            # line, so a raw newline drops the rest of the quote out of it.
            cited_text = " ".join(citation.get("cited_text", "").split())
            doc_title = citation.get("document_title", "")
            location = citation.get("location", "")
            if cited_text:
                if len(cited_text) > 150:
                    cited_text = cited_text[:147] + "..."
                source = doc_title
                if location:
                    source += f", {location}"
                doc_lines.append(f"> {cited_text}\n> — *{source}*")

    sections: list[tuple[str | None, list[str]]] = []
    if web_lines:
        numbered = [f"{index}. {line}" for index, line in enumerate(web_lines[:20], 1)]
        sections.append((None, numbered))
    if doc_lines:
        sections.extend((None, [line]) for line in doc_lines[:10])

    if not sections:
        return

    description = _fit_markdown_sections(sections)
    if not description:
        return

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


def append_fallback_embed(
    embeds: list[Embed],
    requested_model: str,
    served_model: str | None,
) -> None:
    """Append a notice when the refusal fallback served with a different model."""
    if not served_model or served_model == requested_model:
        return
    embeds.append(
        Embed(
            title="Model Fallback",
            description=(
                f"`{requested_model}` declined this request; "
                f"the response was served by `{served_model}` instead."
            ),
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
    """Append the one-line cost embed: request cost, tokens, tool counts and daily total.

    The advisor model's tokens are billed in ``request_cost`` but are not added to the
    token counts; the advisor shows only as a call count.
    """
    tool_counts = (
        (parsed.web_search_requests, "search", "searches"),
        (parsed.web_fetch_requests, "fetch", "fetches"),
        (parsed.code_execution_requests, "code run", None),
        (parsed.advisor_calls, "advisor call", None),
    )
    line = format_cost_line(
        request_cost,
        daily_cost,
        # Anthropic's usage.input_tokens excludes cache reads and cache writes.
        input_tokens=parsed.input_tokens + parsed.cache_read_tokens + parsed.cache_creation_tokens,
        output_tokens=parsed.output_tokens,
        cached_tokens=parsed.cache_read_tokens,
        thinking_tokens=parsed.thinking_tokens,
        details=[count_label(count, one, many) for count, one, many in tool_counts if count],
    )
    embeds.append(Embed(description=line, color=Colour.orange()))


__all__ = [
    "append_citations_embed",
    "append_compaction_embed",
    "append_context_warning_embed",
    "append_fallback_embed",
    "append_pricing_embed",
    "append_response_embeds",
    "append_stop_reason_embed",
    "append_thinking_embeds",
]
