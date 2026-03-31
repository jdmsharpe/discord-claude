from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedResponse:
    """Structured result from parsing an API response."""

    text: str = ""
    thinking: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)
    tool_use_blocks: list[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    web_search_requests: int = 0
    web_fetch_requests: int = 0
    code_execution_requests: int = 0
    context_warning: bool = False
    context_compacted: bool = False


def extract_response_content(response) -> ParsedResponse:
    """Extract response text, thinking, citations, and tool use from an API response."""
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    citations: list[dict[str, str]] = []
    tool_use_blocks: list[Any] = []
    seen_urls: set[str] = set()
    seen_cited_texts: set[str] = set()

    for block in response.content:
        if block.type == "thinking":
            thinking_parts.append(block.thinking)
        elif block.type == "text":
            text_parts.append(block.text)
            block_citations = getattr(block, "citations", None)
            if block_citations:
                for citation in block_citations:
                    url = getattr(citation, "url", None)
                    cited_text = getattr(citation, "cited_text", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append(
                            {
                                "kind": "web",
                                "url": url,
                                "title": getattr(citation, "title", url),
                                "cited_text": cited_text,
                            }
                        )
                    elif not url and cited_text and cited_text not in seen_cited_texts:
                        seen_cited_texts.add(cited_text)
                        doc_title = getattr(citation, "document_title", "Document")
                        location = ""
                        citation_type = getattr(citation, "type", "")
                        if citation_type == "page_location":
                            start = getattr(citation, "start_page_number", None)
                            end = getattr(citation, "end_page_number", None)
                            if start is not None:
                                if end is not None and end > start + 1:
                                    location = f"pp. {start}–{end - 1}"
                                else:
                                    location = f"p. {start}"
                        citations.append(
                            {
                                "kind": "document",
                                "cited_text": cited_text,
                                "document_title": doc_title,
                                "location": location,
                            }
                        )
        elif block.type == "tool_use":
            tool_use_blocks.append(block)
        elif block.type.startswith("mcp_"):
            continue

    response_text = "\n\n".join(text_parts) if text_parts else "No response."
    thinking_text = "\n\n".join(thinking_parts)

    return ParsedResponse(
        text=response_text,
        thinking=thinking_text,
        citations=citations,
        tool_use_blocks=tool_use_blocks,
    )


__all__ = ["ParsedResponse", "extract_response_content"]
