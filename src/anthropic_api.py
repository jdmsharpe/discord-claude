"""Compatibility shim exposing the previous ``anthropic_api`` module path while code migrates."""

from __future__ import annotations

import warnings

from discord_claude import ClaudeCog
from discord_claude.bash_tool import execute_bash_command
from discord_claude.cogs.claude.embeds import (
    append_citations_embed,
    append_compaction_embed,
    append_context_warning_embed,
    append_pricing_embed,
    append_response_embeds,
    append_stop_reason_embed,
    append_thinking_embeds,
)
from discord_claude.cogs.claude.models import ParsedResponse
from discord_claude.cogs.claude.responses import extract_response_content
from discord_claude.memory import execute_memory_operation

_VERSION = "1.x"

warnings.warn(
    "The top-level `anthropic_api` module is deprecated; import from `discord_claude` instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ClaudeCog",
    "ParsedResponse",
    "extract_response_content",
    "append_thinking_embeds",
    "append_response_embeds",
    "append_citations_embed",
    "append_stop_reason_embed",
    "append_context_warning_embed",
    "append_compaction_embed",
    "append_pricing_embed",
    "execute_memory_operation",
    "execute_bash_command",
]
