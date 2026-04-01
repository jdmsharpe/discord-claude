"""Thin Claude cog wrapper around extracted helper modules."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from discord import ApplicationContext, Attachment
from discord.commands import OptionChoice, SlashCommandGroup, option
from discord.ext import commands

from discord_claude.config.auth import GUILD_IDS, SHOW_COST_EMBEDS
from discord_claude.util import ChatCompletionParameters, Conversation, ConversationKey, ToolChoice

from .attachments import (
    SUPPORTED_DOCUMENT_TYPES,
    SUPPORTED_IMAGE_TYPES,
    build_attachment_content_block,
    fetch_attachment_bytes,
)
from .chat import (
    build_api_params,
    build_thinking_config,
    call_api_with_tool_loop,
    compact_conversation,
    handle_check_permissions,
    handle_on_message,
    run_chat_command,
    validate_request_configuration,
)
from .chat import (
    handle_new_message_in_conversation as run_followup_message,
)
from .chat import (
    keep_typing as keep_typing_loop,
)
from .client import (
    APIConnectionError,
    APIError,
    build_claude_client,
    close_http_session,
    get_http_session,
)
from .embeds import (
    append_citations_embed,
    append_compaction_embed,
    append_context_warning_embed,
    append_pricing_embed,
    append_response_embeds,
    append_stop_reason_embed,
    append_thinking_embeds,
)
from .models import ParsedResponse, ToolHandler, UsageTotals
from .responses import extract_response_content
from .state import cleanup_conversation, stop_conversation, strip_previous_view, track_daily_cost
from .tool_handlers import MemoryToolHandler
from .tooling import default_tool_handlers

__all__ = [
    "APIConnectionError",
    "APIError",
    "ClaudeCog",
    "MemoryToolHandler",
    "ParsedResponse",
    "SUPPORTED_DOCUMENT_TYPES",
    "SUPPORTED_IMAGE_TYPES",
    "ToolChoice",
    "UsageTotals",
    "append_citations_embed",
    "append_compaction_embed",
    "append_context_warning_embed",
    "append_pricing_embed",
    "append_response_embeds",
    "append_stop_reason_embed",
    "append_thinking_embeds",
    "build_attachment_content_block",
    "extract_response_content",
]


class ClaudeCog(commands.Cog):
    claude = SlashCommandGroup("claude", "Claude AI commands", guild_ids=GUILD_IDS)

    def __init__(self, bot):
        self.bot = bot
        self.client = build_claude_client()
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)
        self.show_cost_embeds = SHOW_COST_EMBEDS

        self.conversations: dict[ConversationKey, Conversation] = {}
        self.views = {}
        self.last_view_messages = {}
        self.daily_costs: dict[tuple[int, str], float] = {}
        self._http_session = None
        self._session_lock = asyncio.Lock()
        self._tool_handlers: dict[str, ToolHandler] = default_tool_handlers()

    async def _get_http_session(self):
        return await get_http_session(self)

    async def _compact_conversation(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
    ) -> str:
        return await compact_conversation(self, messages, system=system)

    async def _strip_previous_view(self, user) -> None:
        await strip_previous_view(self, user)

    async def _cleanup_conversation(self, user) -> None:
        await cleanup_conversation(self, user)

    async def _stop_conversation(self, conversation_key: ConversationKey, user) -> None:
        await stop_conversation(self, conversation_key, user)

    def _track_daily_cost(
        self,
        user_id: int,
        model: str,
        parsed: ParsedResponse,
    ) -> tuple[float, float]:
        return track_daily_cost(self, user_id, model, parsed)

    async def _fetch_attachment_bytes(self, attachment: Attachment) -> bytes | None:
        return await fetch_attachment_bytes(self, attachment)

    def cog_unload(self):
        close_http_session(self)

    async def _call_api_with_tool_loop(
        self,
        api_params: dict[str, Any],
        messages: list[dict[str, Any]],
        user_id: int,
        max_iterations: int = 10,
    ):
        return await call_api_with_tool_loop(
            self,
            api_params=api_params,
            messages=messages,
            user_id=user_id,
            max_iterations=max_iterations,
        )

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any], user_id: int) -> str:
        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'"
        return await handler.execute(tool_input, user_id)

    def register_tool_handler(self, tool_name: str, handler: ToolHandler) -> None:
        self._tool_handlers[tool_name] = handler

    def unregister_tool_handler(self, tool_name: str) -> ToolHandler | None:
        return self._tool_handlers.pop(tool_name, None)

    @staticmethod
    def _build_thinking_config(params: ChatCompletionParameters) -> dict[str, Any] | None:
        return build_thinking_config(params)

    @classmethod
    def _validate_request_configuration(cls, params: ChatCompletionParameters) -> str | None:
        return validate_request_configuration(params)

    @classmethod
    def _build_api_params(
        cls,
        params: ChatCompletionParameters,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return build_api_params(params, messages)

    async def handle_new_message_in_conversation(self, message, conversation: Conversation):
        await run_followup_message(self, message, conversation)

    async def keep_typing(self, channel):
        await keep_typing_loop(self, channel)

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info("Logged in as %s (ID: %s)", self.bot.user, self.bot.owner_id)
        self.logger.info("Attempting to sync commands for guilds: %s", GUILD_IDS)
        try:
            await self.bot.sync_commands()
            self.logger.info("Commands synchronized successfully.")
        except Exception as error:
            self.logger.error("Error during command synchronization: %s", error, exc_info=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        await handle_on_message(self, message)

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        self.logger.error("Error in event %s: %s %s", event, args, kwargs, exc_info=True)

    @claude.command(
        name="check_permissions",
        description="Check if bot has necessary permissions in this channel",
    )
    async def check_permissions(self, ctx: ApplicationContext):
        await handle_check_permissions(ctx)

    @claude.command(
        name="chat",
        description="Starts a conversation with Claude.",
    )
    @option("prompt", description="Prompt", required=True, type=str)
    @option(
        "system",
        description="System prompt to set Claude's behavior. (default: not set)",
        required=False,
        type=str,
    )
    @option(
        "model",
        description="Choose from the following Claude models. (default: Claude Opus 4.6. warning: Opus is expensive!)",
        required=False,
        choices=[
            OptionChoice(name="Claude Opus 4.6", value="claude-opus-4-6"),
            OptionChoice(name="Claude Sonnet 4.6", value="claude-sonnet-4-6"),
            OptionChoice(name="Claude Opus 4.5", value="claude-opus-4-5"),
            OptionChoice(name="Claude Sonnet 4.5", value="claude-sonnet-4-5"),
            OptionChoice(name="Claude Opus 4.1", value="claude-opus-4-1"),
            OptionChoice(name="Claude Haiku 4.5", value="claude-haiku-4-5"),
        ],
        type=str,
    )
    @option(
        "attachment",
        description="Attach an image (JPEG, PNG, GIF, WEBP), a PDF, a text document, or a code file.",
        required=False,
        type=Attachment,
    )
    @option(
        "max_tokens",
        description="Maximum tokens in the response. (default: 16384)",
        required=False,
        type=int,
    )
    @option(
        "temperature",
        description="(Advanced) Controls the randomness of the model. 0.0 to 1.0. (default: not set)",
        required=False,
        type=float,
    )
    @option(
        "top_p",
        description="(Advanced) Nucleus sampling. 0.0 to 1.0. (default: not set)",
        required=False,
        type=float,
    )
    @option(
        "top_k",
        description="(Advanced) Limits sampling to top K tokens. (default: not set)",
        required=False,
        type=int,
    )
    @option(
        "effort",
        description="Control response effort: low (fast, concise), medium (balanced), high (thorough). (default: not set)",
        required=False,
        choices=[
            OptionChoice(name="Low", value="low"),
            OptionChoice(name="Medium", value="medium"),
            OptionChoice(name="High", value="high"),
        ],
        type=str,
    )
    @option(
        "thinking_budget",
        description="Token budget for extended thinking on non-4.6 models. (default: not set)",
        required=False,
        type=int,
    )
    @option(
        "web_search",
        description="Enable web search to find current information. (default: false)",
        required=False,
        type=bool,
    )
    @option(
        "web_fetch",
        description="Enable web fetch to retrieve full web page content. (default: false)",
        required=False,
        type=bool,
    )
    @option(
        "code_execution",
        description="Enable code execution to run code in a sandbox. (default: false)",
        required=False,
        type=bool,
    )
    @option(
        "memory",
        description="Enable memory to save and recall information across conversations. (default: false)",
        required=False,
        type=bool,
    )
    @option(
        "mcp",
        description="Optional comma-separated MCP preset names to enable for this conversation.",
        required=False,
        type=str,
    )
    @option(
        "tool_choice",
        description="Tool behavior when tools are enabled. (default: Anthropic default)",
        required=False,
        choices=[
            OptionChoice(name="Auto", value="auto"),
            OptionChoice(name="None", value="none"),
        ],
        type=str,
    )
    async def chat(
        self,
        ctx: ApplicationContext,
        prompt: str,
        model: str = "claude-opus-4-6",
        system: str | None = None,
        attachment: Attachment | None = None,
        max_tokens: int = 16384,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        effort: str | None = None,
        thinking_budget: int | None = None,
        web_search: bool = False,
        web_fetch: bool = False,
        code_execution: bool = False,
        memory: bool = False,
        mcp: str | None = None,
        tool_choice: str | None = None,
    ):
        await run_chat_command(
            self,
            ctx=ctx,
            prompt=prompt,
            model=model,
            system=system,
            attachment=attachment,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            effort=effort,
            thinking_budget=thinking_budget,
            web_search=web_search,
            web_fetch=web_fetch,
            code_execution=code_execution,
            memory=memory,
            mcp=mcp,
            tool_choice=tool_choice,
        )
