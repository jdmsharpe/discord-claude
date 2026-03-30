"""Compatibility shim exposing the previous ``anthropic_api`` API while code migrates."""

from __future__ import annotations

import warnings

from discord_claude.bash_tool import execute_bash_command
from discord_claude.cogs.claude import cog as _claude_cog
from discord_claude.memory import execute_memory_operation

_VERSION = "1.x"

AnthropicAPI = _claude_cog.AnthropicAPI
ParsedResponse = _claude_cog.ParsedResponse
extract_response_content = _claude_cog.extract_response_content
append_thinking_embeds = _claude_cog.append_thinking_embeds
append_response_embeds = _claude_cog.append_response_embeds
append_citations_embed = _claude_cog.append_citations_embed
append_stop_reason_embed = _claude_cog.append_stop_reason_embed
append_context_warning_embed = _claude_cog.append_context_warning_embed
append_compaction_embed = _claude_cog.append_compaction_embed
append_pricing_embed = _claude_cog.append_pricing_embed

warnings.warn(
    "The top-level `anthropic_api` module is deprecated; import from `discord_claude` instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "AnthropicAPI",
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
