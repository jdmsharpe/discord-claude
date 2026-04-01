"""Claude cog package exports."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cog import ClaudeCog
    from .embeds import (
        append_citations_embed,
        append_compaction_embed,
        append_context_warning_embed,
        append_pricing_embed,
        append_response_embeds,
        append_stop_reason_embed,
        append_thinking_embeds,
    )
    from .models import ParsedResponse
    from .responses import extract_response_content
    from .tool_handlers import MemoryToolHandler

__all__ = [
    "ClaudeCog",
    "MemoryToolHandler",
    "ParsedResponse",
    "extract_response_content",
    "append_thinking_embeds",
    "append_response_embeds",
    "append_citations_embed",
    "append_stop_reason_embed",
    "append_context_warning_embed",
    "append_compaction_embed",
    "append_pricing_embed",
]

_EMBED_EXPORTS = {
    "append_citations_embed",
    "append_compaction_embed",
    "append_context_warning_embed",
    "append_pricing_embed",
    "append_response_embeds",
    "append_stop_reason_embed",
    "append_thinking_embeds",
}


def __getattr__(name: str):
    if name == "ClaudeCog":
        from .cog import ClaudeCog

        return ClaudeCog
    if name == "MemoryToolHandler":
        from .tool_handlers import MemoryToolHandler

        return MemoryToolHandler
    if name == "ParsedResponse":
        from .models import ParsedResponse

        return ParsedResponse
    if name == "extract_response_content":
        from .responses import extract_response_content

        return extract_response_content
    if name in _EMBED_EXPORTS:
        from . import embeds as _embeds

        return getattr(_embeds, name)
    raise AttributeError(name)
