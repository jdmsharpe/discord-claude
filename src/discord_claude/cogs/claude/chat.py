import asyncio
import contextlib
from typing import Any

import aiohttp
from discord import ApplicationContext, Attachment, Colour, Embed

from discord_claude.config.auth import SHOW_COST_EMBEDS
from discord_claude.config.mcp import parse_mcp_preset_names, resolve_mcp_presets
from discord_claude.util import (
    ADAPTIVE_THINKING_MODELS,
    AVAILABLE_TOOLS,
    CACHE_TTL,
    COMPACTION_MODELS,
    CONTEXT_COMPACTION_THRESHOLD,
    EXTENDED_THINKING_MODELS,
    MODEL_CONTEXT_WINDOWS,
    ChatCompletionParameters,
    Conversation,
    ConversationKey,
    ToolChoice,
    UsageTotals,
    format_anthropic_error,
    truncate_text,
)

from .attachments import build_attachment_content_block, fetch_attachment_bytes
from .embeds import (
    append_citations_embed,
    append_compaction_embed,
    append_context_warning_embed,
    append_pricing_embed,
    append_response_embeds,
    append_stop_reason_embed,
    append_thinking_embeds,
)
from .responses import ParsedResponse, extract_response_content
from .state import compact_conversation, create_button_view
from .tooling import execute_tool


async def keep_typing(cog, channel) -> None:
    """Keep the Discord typing indicator alive while Claude is working."""
    try:
        cog.logger.debug("Starting typing indicator loop in channel %s", channel.id)
        while True:
            async with channel.typing():
                cog.logger.debug("Sent typing indicator to channel %s", channel.id)
                await asyncio.sleep(5)
    except asyncio.CancelledError:
        cog.logger.debug("Typing indicator cancelled for channel %s", channel.id)
        raise


def handle_check_permissions(ctx: ApplicationContext) -> Any:
    """Check whether the bot can read the current server channel."""
    if ctx.guild is None or not hasattr(ctx.channel, "permissions_for"):
        return ctx.respond("This command must be used in a server channel.")
    permissions = ctx.channel.permissions_for(ctx.guild.me)  # type: ignore[union-attr]
    if permissions.read_messages and permissions.read_message_history:
        return ctx.respond("Bot has permission to read messages and message history.")
    return ctx.respond("Bot is missing necessary permissions in this channel.")


def build_thinking_config(params: ChatCompletionParameters) -> dict[str, Any] | None:
    """Return the Anthropic thinking configuration for the current model/settings."""
    if params.model in ADAPTIVE_THINKING_MODELS:
        return {"type": "adaptive", "display": "summarized"}
    if params.thinking_budget is not None and params.model in EXTENDED_THINKING_MODELS:
        return {
            "type": "enabled",
            "budget_tokens": params.thinking_budget,
        }
    return None


def validate_request_configuration(params: ChatCompletionParameters) -> str | None:
    """Validate request options before dispatching to Anthropic."""
    tool_choice = params.tool_choice
    if tool_choice is None:
        return None

    choice_type = tool_choice["type"]
    has_thinking = build_thinking_config(params) is not None

    if has_thinking and choice_type in {"any", "tool"}:
        return (
            "Thinking mode only supports tool behavior `auto` or `none`. "
            "Forced tool modes are not compatible with thinking."
        )

    if choice_type in {"any", "tool"} and not params.tools:
        return "Forced tool behavior requires at least one enabled tool."

    if choice_type == "tool":
        tool_name = tool_choice.get("name")
        if not tool_name:
            return "Tool behavior `tool` requires a tool name."
        if tool_name not in AVAILABLE_TOOLS:
            return f"Unknown forced tool `{tool_name}`."
        if tool_name not in params.tools:
            return (
                f"Tool behavior `tool` requires `{tool_name}` to be enabled in the "
                "conversation tools."
            )

    return None


def build_api_params(
    params: ChatCompletionParameters,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Anthropic API parameter dict from ChatCompletionParameters."""
    api_params: dict[str, Any] = {
        "model": params.model,
        "max_tokens": params.max_tokens,
        "messages": messages,
    }
    thinking_config = build_thinking_config(params)
    if thinking_config is not None:
        api_params["thinking"] = thinking_config
    if params.effort is not None:
        api_params["effort"] = params.effort
    if params.system:
        api_params["system"] = params.system
    if params.temperature is not None:
        api_params["temperature"] = params.temperature
    if params.top_p is not None:
        api_params["top_p"] = params.top_p
    if params.top_k is not None:
        api_params["top_k"] = params.top_k
    mcp_presets, mcp_error = resolve_mcp_presets(params.mcp_preset_names)
    if mcp_error:
        raise ValueError(mcp_error)

    api_tools = [AVAILABLE_TOOLS[tool] for tool in params.tools if tool in AVAILABLE_TOOLS]
    if mcp_presets:
        api_params["mcp_servers"] = []
        for preset in mcp_presets:
            server_config: dict[str, Any] = {
                "type": "url",
                "url": preset.server_url,
                "name": preset.name,
            }
            if preset.authorization_env_var:
                from os import getenv

                authorization_token = getenv(preset.authorization_env_var)
                if authorization_token:
                    server_config["authorization_token"] = authorization_token
            api_params["mcp_servers"].append(server_config)

            toolset: dict[str, Any] = {
                "type": "mcp_toolset",
                "mcp_server_name": preset.name,
            }
            default_config: dict[str, Any] = {}
            if preset.allowed_tools:
                default_config["enabled"] = False
                toolset["configs"] = {
                    tool_name: {"enabled": True} for tool_name in preset.allowed_tools
                }
            if preset.defer_loading:
                default_config["defer_loading"] = True
            if default_config:
                toolset["default_config"] = default_config
            api_tools.append(toolset)

    if api_tools:
        api_params["tools"] = api_tools
        if params.tool_choice is not None:
            api_params["tool_choice"] = params.tool_choice
    return api_params


async def call_api_with_tool_loop(
    cog,
    api_params: dict[str, Any],
    messages: list[dict[str, Any]],
    user_id: int,
    max_iterations: int = 10,
) -> ParsedResponse:
    """Call the Anthropic API, handling tool-use loops and context management."""
    model = api_params.get("model", "")
    use_compaction = model in COMPACTION_MODELS
    has_tools = bool(api_params.get("tools"))
    has_thinking = bool(api_params.get("thinking"))
    has_mcp = bool(api_params.get("mcp_servers"))

    betas: list[str] = []
    edits: list[dict[str, Any]] = []
    if has_thinking:
        edits.append(
            {
                "type": "clear_thinking_20251015",
                "keep": {"type": "thinking_turns", "value": 2},
            }
        )
    if has_tools:
        edits.append(
            {
                "type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 50000},
                "keep": {"type": "tool_uses", "value": 5},
            }
        )
    if edits:
        betas.append("context-management-2025-06-27")
    if has_mcp:
        betas.append("mcp-client-2025-11-20")
    if use_compaction:
        betas.append("compact-2026-01-12")
        edits.append({"type": "compact_20260112"})

    totals = UsageTotals()
    context_window = MODEL_CONTEXT_WINDOWS.get(model, 200_000)
    parsed: ParsedResponse | None = None

    for iteration in range(max_iterations):
        if (
            not use_compaction
            and totals.input_tokens > context_window * CONTEXT_COMPACTION_THRESHOLD
            and len(messages) > 1
        ):
            cog.logger.info(
                "Input tokens (%d) exceeded %.0f%% of context window (%d), compacting...",
                totals.input_tokens,
                CONTEXT_COMPACTION_THRESHOLD * 100,
                context_window,
            )
            await compact_conversation(cog, messages, system=api_params.get("system"))
            totals.context_compacted = True

        api_params["messages"] = messages
        if betas:
            response = await cog.client.beta.messages.create(  # type: ignore[call-overload]
                **api_params,
                betas=betas,
                context_management={"edits": edits} if edits else None,  # type: ignore[arg-type]
                cache_control={"type": "ephemeral", "ttl": CACHE_TTL},
            )
        else:
            response = await cog.client.messages.create(
                **api_params,
                cache_control={"type": "ephemeral", "ttl": CACHE_TTL},
            )

        parsed = extract_response_content(response)
        parsed.stop_reason = response.stop_reason
        totals.accumulate(getattr(response, "usage", None))

        if response.stop_reason == "end_turn":
            messages.append({"role": "assistant", "content": response.content})
            totals.apply_to(parsed, context_window)
            return parsed
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            cog.logger.info("pause_turn received, continuing (iteration %d)", iteration + 1)
            continue
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for tool_block in parsed.tool_use_blocks:
                result_text = await execute_tool(tool_block.name, tool_block.input, user_id)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": result_text,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
            cog.logger.info("tool_use handled, re-sending (iteration %d)", iteration + 1)
            continue

        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason not in (
            "max_tokens",
            "refusal",
            "model_context_window_exceeded",
        ):
            cog.logger.warning("Unknown stop_reason: %s", response.stop_reason)
        totals.apply_to(parsed, context_window)
        return parsed

    cog.logger.warning("Tool loop hit max_iterations (%d)", max_iterations)
    if parsed is None:
        raise RuntimeError("Tool loop completed without any API response")
    totals.apply_to(parsed, context_window)
    return parsed


async def handle_new_message_in_conversation(cog, message, conversation: Conversation) -> None:
    """Handle a new Discord message in an ongoing Claude conversation."""
    params = conversation.params
    messages = conversation.messages

    cog.logger.info("Handling new message in conversation %s.", params.conversation_id)
    typing_task = None
    embeds = []

    try:
        if message.author != params.conversation_starter or params.paused:
            return

        validation_error = validate_request_configuration(params)
        if validation_error:
            await message.reply(
                embed=Embed(
                    title="Unsupported Tool Configuration",
                    description=validation_error,
                    color=Colour.red(),
                )
            )
            return

        typing_task = asyncio.create_task(keep_typing(cog, message.channel))

        user_content: list[dict[str, Any]] = []
        if message.content:
            user_content.append({"type": "text", "text": message.content})
        if message.attachments:
            for attachment in message.attachments:
                attachment_data = await fetch_attachment_bytes(cog, attachment)
                if attachment_data is not None:
                    content_block = build_attachment_content_block(
                        attachment.content_type or "",
                        attachment_data,
                        attachment.filename,
                    )
                    if content_block:
                        user_content.append(content_block)

        messages.append({"role": "user", "content": user_content})
        api_params = build_api_params(params, messages)
        parsed = await call_api_with_tool_loop(
            cog,
            api_params=api_params,
            messages=messages,
            user_id=message.author.id,
        )
        response_text = parsed.text

        if typing_task:
            typing_task.cancel()
            typing_task = None

        append_thinking_embeds(embeds, parsed.thinking)
        append_response_embeds(embeds, response_text)
        append_stop_reason_embed(embeds, parsed.stop_reason)
        if parsed.context_compacted:
            append_compaction_embed(embeds)
        if parsed.context_warning:
            append_context_warning_embed(embeds)
        append_citations_embed(embeds, parsed.citations)

        request_cost, daily_cost = cog._track_daily_cost(message.author.id, params.model, parsed)
        if SHOW_COST_EMBEDS:
            append_pricing_embed(embeds, parsed, request_cost, daily_cost)

        if conversation.params.conversation_id is None:
            cog.logger.error("Conversation ID is None, cannot track message")
            return

        await cog._strip_previous_view(message.author)
        view = cog.views.get(message.author)

        if embeds:
            try:
                reply_message = await message.reply(embeds=embeds, view=view)
                cog.last_view_messages[message.author] = reply_message
            except Exception as embed_error:
                cog.logger.warning("Embed failed, sending as text: %s", embed_error)
                safe_response_text = response_text or "No response text available"
                reply_message = await message.reply(
                    content=f"**Response:**\n{safe_response_text[:1900]}{'...' if len(safe_response_text) > 1900 else ''}",
                    view=view,
                )
                cog.last_view_messages[message.author] = reply_message
        else:
            reply_message = await message.reply(
                content="An error occurred: No content to send.",
                view=view,
            )
            cog.last_view_messages[message.author] = reply_message

    except Exception as error:
        if isinstance(error, aiohttp.ClientError):
            description = format_anthropic_error(error)
            cog.logger.error(
                "API error in handle_new_message_in_conversation: %s",
                description,
                exc_info=True,
            )
            if len(description) > 4000:
                description = description[:4000] + "\n\n... (error message truncated)"
            await cog._cleanup_conversation(message.author)
            await message.reply(
                embed=Embed(title="Error", description=description, color=Colour.red())
            )
            conv_key = (message.author.id, message.channel.id)
            cog.conversations.pop(conv_key, None)
            return

        description = format_anthropic_error(error)
        cog.logger.error(
            "Unexpected error in handle_new_message_in_conversation: %s",
            error,
            exc_info=True,
        )
        await cog._cleanup_conversation(message.author)
        conv_key = (message.author.id, message.channel.id)
        cog.conversations.pop(conv_key, None)
        with contextlib.suppress(Exception):
            await message.reply(
                embed=Embed(
                    title="Error",
                    description=f"An unexpected error occurred: {type(error).__name__}",
                    color=Colour.red(),
                )
            )
    finally:
        if typing_task:
            typing_task.cancel()


async def handle_on_message(cog, message) -> None:
    """Process Discord messages that belong to active Claude conversations."""
    if message.author == cog.bot.user:
        return

    cog.logger.debug(
        "Received message from %s in channel %s: %r",
        message.author,
        message.channel.id,
        message.content,
    )
    conv_key: ConversationKey = (message.author.id, message.channel.id)
    conversation = cog.conversations.get(conv_key)
    if conversation is not None:
        cog.logger.info(
            "Processing followup message for conversation %s",
            conversation.params.conversation_id,
        )
        await handle_new_message_in_conversation(cog, message, conversation)


async def run_chat_command(
    cog,
    ctx: ApplicationContext,
    *,
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
) -> None:
    """Run the /claude chat command."""
    await ctx.defer()
    typing_task = None

    if ctx.channel is None:
        await ctx.send_followup(
            embed=Embed(
                title="Error",
                description="Cannot start conversation: channel context is unavailable.",
                color=Colour.red(),
            )
        )
        return

    if (ctx.author.id, ctx.channel.id) in cog.conversations:
        await ctx.send_followup(
            embed=Embed(
                title="Error",
                description="You already have an active conversation in this channel. Please finish it before starting a new one.",
                color=Colour.red(),
            )
        )
        return

    try:
        typing_task = asyncio.create_task(keep_typing(cog, ctx.channel))

        enabled_tools: list[str] = []
        if web_search:
            enabled_tools.append("web_search")
        if web_fetch:
            enabled_tools.append("web_fetch")
        if code_execution:
            enabled_tools.append("code_execution")
        if memory:
            enabled_tools.append("memory")
        mcp_preset_names = parse_mcp_preset_names(mcp)
        _, mcp_error = resolve_mcp_presets(mcp_preset_names)
        if mcp_error:
            await ctx.send_followup(
                embed=Embed(
                    title="Error",
                    description=mcp_error,
                    color=Colour.red(),
                )
            )
            return

        resolved_tool_choice: ToolChoice | None = None
        if tool_choice == "auto":
            resolved_tool_choice = {"type": "auto"}
        elif tool_choice == "none":
            resolved_tool_choice = {"type": "none"}
        if mcp_preset_names and resolved_tool_choice == {"type": "none"}:
            resolved_tool_choice = {"type": "auto"}

        user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if attachment:
            attachment_data = await fetch_attachment_bytes(cog, attachment)
            if attachment_data is not None:
                content_block = build_attachment_content_block(
                    attachment.content_type or "",
                    attachment_data,
                    attachment.filename,
                )
                if content_block:
                    user_content.append(content_block)

        conversation_messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        params = ChatCompletionParameters(
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            effort=effort,
            thinking_budget=thinking_budget,
            conversation_starter=ctx.author,
            channel_id=ctx.channel.id,
            conversation_id=ctx.interaction.id,
            tools=enabled_tools,
            mcp_preset_names=mcp_preset_names,
            tool_choice=resolved_tool_choice,
        )

        validation_error = validate_request_configuration(params)
        if validation_error:
            await ctx.send_followup(
                embed=Embed(
                    title="Unsupported Tool Configuration",
                    description=validation_error,
                    color=Colour.red(),
                )
            )
            return

        api_params = build_api_params(params, conversation_messages)
        parsed = await call_api_with_tool_loop(
            cog,
            api_params=api_params,
            messages=conversation_messages,
            user_id=ctx.author.id,
        )
        response_text = parsed.text

        description = f"**Prompt:** {truncate_text(prompt, 2000)}\n"
        description += f"**Model:** {model}\n"
        if system:
            description += f"**System:** {truncate_text(system, 500)}\n"
        description += f"**Max Tokens:** {max_tokens}\n"
        if temperature is not None:
            description += f"**Temperature:** {temperature}\n"
        if top_p is not None:
            description += f"**Top P:** {top_p}\n"
        if top_k is not None:
            description += f"**Top K:** {top_k}\n"
        if effort is not None:
            description += f"**Effort:** {effort}\n"
        if thinking_budget is not None:
            description += f"**Thinking Budget:** {thinking_budget} tokens\n"
        if enabled_tools:
            description += f"**Tools:** {', '.join(enabled_tools)}\n"
        if mcp_preset_names:
            description += f"**MCP Presets:** {', '.join(mcp_preset_names)}\n"
        if resolved_tool_choice is not None:
            description += f"**Tool Choice:** {resolved_tool_choice['type']}\n"

        embeds = [
            Embed(
                title="Conversation Started",
                description=description,
                color=Colour.green(),
            )
        ]
        if mcp_preset_names:
            embeds.append(
                Embed(
                    title="MCP Enabled",
                    description=(
                        "Trusted MCP presets are active for this conversation. "
                        "Only enable servers you trust, because tool calls can share conversation data with them."
                    ),
                    color=Colour.orange(),
                )
            )
        append_thinking_embeds(embeds, parsed.thinking)
        append_response_embeds(embeds, response_text)
        append_stop_reason_embed(embeds, parsed.stop_reason)
        if parsed.context_compacted:
            append_compaction_embed(embeds)
        if parsed.context_warning:
            append_context_warning_embed(embeds)
        append_citations_embed(embeds, parsed.citations)

        request_cost, daily_cost = cog._track_daily_cost(ctx.author.id, model, parsed)
        if SHOW_COST_EMBEDS:
            append_pricing_embed(embeds, parsed, request_cost, daily_cost)

        if len(embeds) == 1:
            await ctx.send_followup("No response generated.")
            return

        await cog._strip_previous_view(ctx.author)

        conv_key: ConversationKey = (ctx.author.id, ctx.channel.id)
        view = create_button_view(
            cog,
            user=ctx.author,
            conversation_key=conv_key,
            initial_tools=enabled_tools,
            initial_tool_choice=resolved_tool_choice,
        )

        message = await ctx.send_followup(embeds=embeds, view=view)
        cog.last_view_messages[ctx.author] = message

        conversation = Conversation(params=params, messages=conversation_messages)
        cog.conversations[conv_key] = conversation

    except Exception as error:
        description = format_anthropic_error(error)
        cog.logger.error("Unexpected error in chat: %s", error, exc_info=True)
        await cog._cleanup_conversation(ctx.author)
        with contextlib.suppress(Exception):
            await ctx.send_followup(
                embed=Embed(
                    title="Error",
                    description=description
                    if description
                    else f"An unexpected error occurred: {type(error).__name__}",
                    color=Colour.red(),
                )
            )
    finally:
        if typing_task:
            typing_task.cancel()


__all__ = [
    "build_api_params",
    "build_thinking_config",
    "call_api_with_tool_loop",
    "handle_check_permissions",
    "handle_new_message_in_conversation",
    "handle_on_message",
    "keep_typing",
    "run_chat_command",
    "validate_request_configuration",
]
