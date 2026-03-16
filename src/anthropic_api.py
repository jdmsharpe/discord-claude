# Standard library imports
import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Third-party imports
import aiohttp

# Anthropic imports
from anthropic import AsyncAnthropic

# Discord imports
from discord import Attachment, Colour, Embed
from discord.commands import (
    ApplicationContext,
    OptionChoice,
    SlashCommandGroup,
    option,
)
from discord.ext import commands

# Local imports
from button_view import ButtonView
from config.auth import ANTHROPIC_API_KEY, GUILD_IDS, SHOW_COST_EMBEDS
from memory import execute_memory_operation
from util import (
    ADAPTIVE_THINKING_MODELS,
    AVAILABLE_TOOLS,
    COMPACTION_MODELS,
    EXTENDED_THINKING_MODELS,
    MODEL_PRICING,
    ChatCompletionParameters,
    Conversation,
    calculate_cost,
    chunk_text,
    format_anthropic_error,
    truncate_text,
)

# Supported attachment MIME types
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SUPPORTED_DOCUMENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
}


def build_attachment_content_block(
    content_type: str, data: bytes, filename: str | None = None
) -> dict[str, Any] | None:
    """
    Build the appropriate content block for an attachment based on its MIME type.

    Args:
        content_type: The MIME type of the attachment
        data: The raw bytes of the attachment
        filename: Optional filename for context

    Returns:
        A content block dict for the Anthropic API, or None if unsupported
    """
    if content_type in SUPPORTED_IMAGE_TYPES:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": content_type,
                "data": base64.b64encode(data).decode("utf-8"),
            },
        }
    elif content_type == "application/pdf":
        block: dict[str, Any] = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(data).decode("utf-8"),
            },
            "citations": {"enabled": True},
        }
        if filename:
            block["title"] = filename
        return block
    elif content_type in SUPPORTED_DOCUMENT_TYPES or (
        content_type and content_type.startswith("text/")
    ):
        # Send as a citable document block
        try:
            text_content = data.decode("utf-8")
        except UnicodeDecodeError:
            text_content = data.decode("latin-1")

        text_block: dict[str, Any] = {
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": text_content,
            },
            "citations": {"enabled": True},
        }
        if filename:
            text_block["title"] = filename
        return text_block
    return None


@dataclass
class ParsedResponse:
    """Structured result from parsing an API response."""

    text: str = ""
    thinking: str = ""
    citations: list[dict[str, str]] = field(default_factory=list)
    has_tool_use: bool = False
    tool_use_blocks: list[Any] = field(default_factory=list)
    raw_content: list[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


def extract_response_content(response) -> ParsedResponse:
    """Extract response text, thinking, citations, and tool use from an API response.

    Returns:
        A ParsedResponse with text, thinking, citations, tool use blocks, and raw content.
    """
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
            # Extract citations from text blocks
            block_citations = getattr(block, "citations", None)
            if block_citations:
                for citation in block_citations:
                    url = getattr(citation, "url", None)
                    cited_text = getattr(citation, "cited_text", "")
                    if url and url not in seen_urls:
                        # Web search citation
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
                        # Document citation (char_location, page_location, content_block_location)
                        seen_cited_texts.add(cited_text)
                        doc_title = getattr(citation, "document_title", "Document")
                        location = ""
                        citation_type = getattr(citation, "type", "")
                        if citation_type == "page_location":
                            start = getattr(citation, "start_page_number", None)
                            end = getattr(citation, "end_page_number", None)
                            if start is not None:
                                if end is not None and end > start + 1:
                                    location = f"pp. {start}\u2013{end - 1}"
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
        # Skip server-side blocks: server_tool_use, web_search_tool_result,
        # web_fetch_tool_result, bash_code_execution_tool_result,
        # text_editor_code_execution_tool_result, redacted_thinking,
        # compaction (context summary from server-side compaction)

    response_text = "\n\n".join(text_parts) if text_parts else "No response."
    thinking_text = "\n\n".join(thinking_parts)

    return ParsedResponse(
        text=response_text,
        thinking=thinking_text,
        citations=citations,
        has_tool_use=len(tool_use_blocks) > 0,
        tool_use_blocks=tool_use_blocks,
        raw_content=response.content,
    )


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
    # If response is extremely long (>20000 chars), truncate it to prevent too many embeds
    if len(response_text) > 20000:
        response_text = (
            response_text[:19500] + "\n\n... [Response truncated due to length]"
        )

    for index, chunk in enumerate(chunk_text(response_text, 3500), start=1):
        embeds.append(
            Embed(
                title="Response" + (f" (Part {index})" if index > 1 else ""),
                description=chunk,
                color=Colour.orange(),
            )
        )


def append_citations_embed(
    embeds: list[Embed], citations: list[dict[str, str]]
) -> None:
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
                doc_lines.append(f"> {cited_text}\n> \u2014 *{source}*")

    parts = []
    if web_lines:
        numbered = [f"{i}. {line}" for i, line in enumerate(web_lines[:20], 1)]
        parts.append("\n".join(numbered))
    if doc_lines:
        parts.append("\n\n".join(doc_lines[:10]))

    if not parts:
        return

    description = "\n\n".join(parts)

    # Respect Discord's embed limits
    current_total = sum(
        len(embed.description or "") + len(embed.title or "") for embed in embeds
    )
    remaining_chars = 6000 - current_total - len("Sources")

    if remaining_chars < 50:
        return

    max_description_length = min(4000, remaining_chars)
    if len(description) > max_description_length:
        description = description[: max_description_length - 3] + "..."

    embeds.append(
        Embed(
            title="Sources",
            description=description,
            color=Colour.blue(),
        )
    )


def append_stop_reason_embed(embeds: list[Embed], stop_reason: str) -> None:
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
        embeds.append(
            Embed(
                title="Request Declined",
                description="Claude was unable to fulfill this request.",
                color=Colour.yellow(),
            )
        )


def append_pricing_embed(
    embeds: list[Embed],
    model: str,
    input_tokens: int,
    output_tokens: int,
    daily_cost: float,
) -> None:
    """Append a compact pricing embed showing cost and token usage."""
    cost = calculate_cost(model, input_tokens, output_tokens)
    description = (
        f"${cost:.4f} · {input_tokens:,} tokens in / {output_tokens:,} tokens out · daily ${daily_cost:.2f}"
    )
    embeds.append(Embed(description=description, color=Colour.orange()))


class AnthropicAPI(commands.Cog):
    # Slash command group for all Claude commands: /claude <subcommand>
    claude = SlashCommandGroup(
        "claude", "Claude AI commands", guild_ids=GUILD_IDS
    )

    def __init__(self, bot):
        """
        Initialize the AnthropicAPI class.

        Args:
            bot: The bot instance.
        """
        self.bot = bot
        self.client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

        # Dictionary to store conversation state for each chat interaction
        self.conversations: dict[int, Conversation] = {}
        # Dictionary to map any message ID to the main conversation ID for tracking
        self.message_to_conversation_id: dict[int, int] = {}
        # Dictionary to store UI views for each conversation
        self.views = {}
        # Daily cost tracking: (user_id, date_iso) -> cumulative cost
        self.daily_costs: dict[tuple[int, str], float] = {}
        self._http_session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session and not self._http_session.closed:
            return self._http_session
        async with self._session_lock:
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()
            return self._http_session

    def _track_daily_cost(
        self, user_id: int, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Add this request's cost to the user's daily total and return the new daily total."""
        cost = calculate_cost(model, input_tokens, output_tokens)
        key = (user_id, date.today().isoformat())
        self.daily_costs[key] = self.daily_costs.get(key, 0.0) + cost
        return self.daily_costs[key]

    async def _fetch_attachment_bytes(self, attachment: Attachment) -> bytes | None:
        session = await self._get_http_session()
        try:
            async with session.get(attachment.url) as response:
                if response.status == 200:
                    return await response.read()
                self.logger.warning(
                    "Failed to fetch attachment %s: HTTP %s",
                    attachment.url,
                    response.status,
                )
        except aiohttp.ClientError as error:
            self.logger.warning(
                "Error fetching attachment %s: %s", attachment.url, error
            )
        return None

    def cog_unload(self):
        loop = getattr(self.bot, "loop", None)

        # Close HTTP session
        session = self._http_session
        if session and not session.closed:
            if loop and loop.is_running():
                loop.create_task(session.close())
            else:
                new_loop = asyncio.new_event_loop()
                try:
                    new_loop.run_until_complete(session.close())
                finally:
                    new_loop.close()
        self._http_session = None

    async def _call_api_with_tool_loop(
        self,
        api_params: dict[str, Any],
        messages: list[dict[str, Any]],
        user_id: int,
        max_iterations: int = 10,
    ) -> ParsedResponse:
        """Call the Anthropic API, handling tool use loops.

        For server-side tools (web_search, web_fetch, code_execution), the API
        handles execution internally. We only need to handle:
        1. stop_reason == "pause_turn": re-send to continue the turn
        2. stop_reason == "tool_use": execute client-side tools (memory),
           append tool_result, re-send

        The messages list is mutated in place. On completion, the final assistant
        message (with full content blocks) is appended to messages.

        Args:
            api_params: The API parameters dict (model, max_tokens, tools, etc.)
            messages: The conversation messages list (mutated in place)
            user_id: The Discord user ID (for memory tool file paths)
            max_iterations: Safety limit on loop iterations

        Returns:
            The final ParsedResponse after all tool loops complete.
        """
        # Use beta API with compaction for supported models
        model = api_params.get("model", "")
        use_compaction = model in COMPACTION_MODELS

        total_input_tokens = 0
        total_output_tokens = 0

        for iteration in range(max_iterations):
            api_params["messages"] = messages
            if use_compaction:
                response = await self.client.beta.messages.create(
                    **api_params,
                    betas=["compact-2026-01-12"],
                    context_management={
                        "edits": [{"type": "compact_20260112"}]
                    },
                )
            else:
                response = await self.client.messages.create(**api_params)
            parsed = extract_response_content(response)
            parsed.stop_reason = response.stop_reason

            # Accumulate token usage across iterations
            usage = getattr(response, "usage", None)
            if usage:
                total_input_tokens += getattr(usage, "input_tokens", 0)
                total_output_tokens += getattr(usage, "output_tokens", 0)

            if response.stop_reason == "end_turn":
                messages.append(
                    {"role": "assistant", "content": response.content}
                )
                parsed.input_tokens = total_input_tokens
                parsed.output_tokens = total_output_tokens
                return parsed

            elif response.stop_reason == "pause_turn":
                messages.append(
                    {"role": "assistant", "content": response.content}
                )
                self.logger.info(
                    f"pause_turn received, continuing (iteration {iteration + 1})"
                )
                continue

            elif response.stop_reason == "tool_use":
                messages.append(
                    {"role": "assistant", "content": response.content}
                )

                tool_results = []
                for tool_block in parsed.tool_use_blocks:
                    result_text = self._execute_tool(
                        tool_block.name, tool_block.input, user_id
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": result_text,
                        }
                    )

                messages.append({"role": "user", "content": tool_results})
                self.logger.info(
                    f"tool_use handled, re-sending (iteration {iteration + 1})"
                )
                continue

            else:
                # max_tokens, refusal, model_context_window_exceeded, or unknown
                messages.append(
                    {"role": "assistant", "content": response.content}
                )
                if response.stop_reason not in (
                    "max_tokens",
                    "refusal",
                    "model_context_window_exceeded",
                ):
                    self.logger.warning(
                        f"Unknown stop_reason: {response.stop_reason}"
                    )
                parsed.input_tokens = total_input_tokens
                parsed.output_tokens = total_output_tokens
                return parsed

        self.logger.warning(
            f"Tool loop hit max_iterations ({max_iterations})"
        )
        parsed.input_tokens = total_input_tokens
        parsed.output_tokens = total_output_tokens
        return parsed

    def _execute_tool(
        self, tool_name: str, tool_input: dict[str, Any], user_id: int
    ) -> str:
        """Execute a client-side tool and return the result string."""
        if tool_name == "memory":
            return execute_memory_operation(user_id=user_id, tool_input=tool_input)
        return f"Error: Unknown tool '{tool_name}'"

    async def handle_new_message_in_conversation(
        self, message, conversation: Conversation
    ):
        """
        Handles a new message in an ongoing conversation.

        Args:
            message: The incoming Discord Message object.
            conversation: The conversation object.
        """
        params = conversation.params
        messages = conversation.messages

        self.logger.info(
            f"Handling new message in conversation {params.conversation_id}."
        )
        typing_task = None
        embeds = []

        try:
            # Only respond to the user who started the conversation and if not paused.
            if message.author != params.conversation_starter or params.paused:
                return

            self.logger.debug(
                f"Starting typing indicator for followup message from {message.author}"
            )
            typing_task = asyncio.create_task(self.keep_typing(message.channel))

            # Build user message content with support for multiple attachments
            user_content: list[dict[str, Any]] = [
                {"type": "text", "text": message.content}
            ]
            if message.attachments:
                for attachment in message.attachments:
                    attachment_data = await self._fetch_attachment_bytes(attachment)
                    if attachment_data is not None:
                        content_block = build_attachment_content_block(
                            attachment.content_type or "",
                            attachment_data,
                            attachment.filename,
                        )
                        if content_block:
                            user_content.append(content_block)

            messages.append({"role": "user", "content": user_content})

            self.logger.debug(f"Sending messages to Claude: {len(messages)} messages")

            # Build API call parameters
            api_params: dict[str, Any] = {
                "model": params.model,
                "max_tokens": params.max_tokens,
                "messages": messages,
            }
            if params.model in ADAPTIVE_THINKING_MODELS:
                api_params["thinking"] = {"type": "adaptive"}
            elif (
                params.thinking_budget is not None
                and params.model in EXTENDED_THINKING_MODELS
            ):
                api_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": params.thinking_budget,
                }
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
            if params.tools:
                api_params["tools"] = [
                    AVAILABLE_TOOLS[t]
                    for t in params.tools
                    if t in AVAILABLE_TOOLS
                ]

            parsed = await self._call_api_with_tool_loop(
                api_params=api_params,
                messages=messages,
                user_id=message.author.id,
            )
            response_text = parsed.text
            thinking_text = parsed.thinking
            self.logger.debug(
                f"Received response from Claude: {response_text[:200]}..."
            )

            # Stop typing indicator as soon as we have the response
            if typing_task:
                self.logger.debug(
                    f"Stopping typing indicator for conversation {params.conversation_id}"
                )
                typing_task.cancel()
                typing_task = None

            append_thinking_embeds(embeds, thinking_text)
            append_response_embeds(embeds, response_text)
            append_citations_embed(embeds, parsed.citations)
            append_stop_reason_embed(embeds, parsed.stop_reason)
            if SHOW_COST_EMBEDS:
                daily_cost = self._track_daily_cost(
                    message.author.id, params.model, parsed.input_tokens, parsed.output_tokens
                )
                append_pricing_embed(
                    embeds, params.model, parsed.input_tokens, parsed.output_tokens, daily_cost
                )

            view = self.views.get(message.author)
            main_conversation_id = conversation.params.conversation_id

            if main_conversation_id is None:
                self.logger.error("Conversation ID is None, cannot track message")
                return

            if embeds:
                try:
                    reply_message = await message.reply(embed=embeds[0], view=view)
                    self.message_to_conversation_id[reply_message.id] = (
                        main_conversation_id
                    )
                except Exception as embed_error:
                    self.logger.warning(f"Embed failed, sending as text: {embed_error}")
                    safe_response_text = response_text or "No response text available"
                    reply_message = await message.reply(
                        content=f"**Response:**\n{safe_response_text[:1900]}{'...' if len(safe_response_text) > 1900 else ''}",
                        view=view,
                    )
                    self.message_to_conversation_id[reply_message.id] = (
                        main_conversation_id
                    )

                for embed in embeds[1:]:
                    try:
                        followup_message = await message.channel.send(
                            embed=embed, view=view
                        )
                        self.message_to_conversation_id[followup_message.id] = (
                            main_conversation_id
                        )
                    except Exception as embed_error:
                        self.logger.warning(f"Followup embed failed: {embed_error}")
                        followup_message = await message.channel.send(
                            content=f"**Response (continued):**\n{embed.description[:1900]}{'...' if len(embed.description) > 1900 else ''}",
                            view=view,
                        )
                        self.message_to_conversation_id[followup_message.id] = (
                            main_conversation_id
                        )

                self.logger.debug("Replied with generated response.")
            else:
                self.logger.warning("No embeds to send in the reply.")
                await message.reply(
                    content="An error occurred: No content to send.",
                    view=view,
                )

        except Exception as e:
            description = format_anthropic_error(e)
            self.logger.error(
                f"Error in handle_new_message_in_conversation: {description}",
                exc_info=True,
            )
            if len(description) > 4000:
                description = description[:4000] + "\n\n... (error message truncated)"
            await message.reply(
                embed=Embed(title="Error", description=description, color=Colour.red())
            )

        finally:
            if typing_task:
                typing_task.cancel()

    async def keep_typing(self, channel):
        """
        Coroutine to keep the typing indicator alive in a channel.

        Args:
            channel: The Discord channel object.
        """
        try:
            self.logger.debug(f"Starting typing indicator loop in channel {channel.id}")
            while True:
                async with channel.typing():
                    self.logger.debug(f"Sent typing indicator to channel {channel.id}")
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            self.logger.debug(f"Typing indicator cancelled for channel {channel.id}")
            raise

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Event listener that runs when the bot is ready.
        Logs bot details and attempts to synchronize commands.
        """
        self.logger.info(f"Logged in as {self.bot.user} (ID: {self.bot.owner_id})")
        self.logger.info(f"Attempting to sync commands for guilds: {GUILD_IDS}")
        try:
            await self.bot.sync_commands()
            self.logger.info("Commands synchronized successfully.")
        except Exception as e:
            self.logger.error(
                f"Error during command synchronization: {e}", exc_info=True
            )

    @commands.Cog.listener()
    async def on_message(self, message):
        """
        Event listener that runs when a message is sent.
        Generates a response using Claude when a new message from the conversation author is detected.

        Args:
            message: The incoming Discord Message object.
        """
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        self.logger.debug(
            f"Received message from {message.author} in channel {message.channel.id}: '{message.content}'"
        )

        # Check for active conversations in this channel
        for conversation in self.conversations.values():
            # Skip conversations that are not in the same channel
            if message.channel.id != conversation.params.channel_id:
                continue

            # Skip if the message is not from the conversation starter
            if message.author != conversation.params.conversation_starter:
                continue

            self.logger.info(
                f"Processing followup message for conversation {conversation.params.conversation_id}"
            )
            await self.handle_new_message_in_conversation(message, conversation)
            break

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        """
        Event listener that runs when an error occurs.
        """
        self.logger.error(f"Error in event {event}: {args} {kwargs}", exc_info=True)

    @claude.command(
        name="check_permissions",
        description="Check if bot has necessary permissions in this channel",
    )
    async def check_permissions(self, ctx: ApplicationContext):
        """
        Checks and reports the bot's permissions in the current channel.
        """
        permissions = ctx.channel.permissions_for(ctx.guild.me)
        if permissions.read_messages and permissions.read_message_history:
            await ctx.respond(
                "Bot has permission to read messages and message history."
            )
        else:
            await ctx.respond("Bot is missing necessary permissions in this channel.")

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
        description="Choose from the following Claude models. (default: Claude Sonnet 4.6)",
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
        description="Attach an image (JPEG, PNG, GIF, WEBP), a PDF, or a text file (TXT, MD, CSV).",
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
    async def chat(
        self,
        ctx: ApplicationContext,
        prompt: str,
        model: str = "claude-sonnet-4-6",
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
    ):
        """
        Creates a persistent conversation session with Claude.

        Initiates an interactive conversation with context preservation across multiple exchanges.
        Supports multimodal inputs (text + images) and provides interactive UI controls for
        conversation management.

        Args:
            ctx: Discord application context
            prompt: Initial conversation prompt or question
            model: Claude model variant (default: claude-sonnet-4-6)
            system: Optional system prompt to set Claude's behavior
            attachment: Optional image attachment for multimodal input
            max_tokens: Maximum tokens in the response (default: 16384)
            temperature: Amount of randomness (0.0-1.0, default 1.0). Use lower for analytical tasks, higher for creative tasks
            top_p: Nucleus sampling threshold (0.0-1.0). Use temperature OR top_p, not both. Advanced use only
            top_k: Only sample from top K tokens. Use temperature OR top_k, not both. Advanced use only

        Returns:
            Discord response with initial AI message and interactive conversation controls

        Note:
            Only one conversation per user per channel allowed. Conversations persist until
            explicitly ended or bot restarts. Follow-up messages automatically handled.
        """
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

        for conv in self.conversations.values():
            if (
                conv.params.conversation_starter == ctx.author
                and conv.params.channel_id == ctx.channel.id
            ):
                await ctx.send_followup(
                    embed=Embed(
                        title="Error",
                        description="You already have an active conversation in this channel. Please finish it before starting a new one.",
                        color=Colour.red(),
                    )
                )
                return

        try:
            typing_task = asyncio.create_task(self.keep_typing(ctx.channel))

            # Build enabled tools list from boolean options
            enabled_tools: list[str] = []
            if web_search:
                enabled_tools.append("web_search")
            if web_fetch:
                enabled_tools.append("web_fetch")
            if code_execution:
                enabled_tools.append("code_execution")
            if memory:
                enabled_tools.append("memory")

            # Build user content with optional attachment (image, PDF, or text file)
            user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            if attachment:
                attachment_data = await self._fetch_attachment_bytes(attachment)
                if attachment_data is not None:
                    content_block = build_attachment_content_block(
                        attachment.content_type or "",
                        attachment_data,
                        attachment.filename,
                    )
                    if content_block:
                        user_content.append(content_block)

            # Build initial messages list (will be mutated by tool loop)
            conversation_messages: list[dict[str, Any]] = [
                {"role": "user", "content": user_content}
            ]

            # Build API call parameters
            api_params: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": conversation_messages,
            }
            if model in ADAPTIVE_THINKING_MODELS:
                api_params["thinking"] = {"type": "adaptive"}
            elif thinking_budget is not None and model in EXTENDED_THINKING_MODELS:
                api_params["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                }
            if effort is not None:
                api_params["effort"] = effort
            if system:
                api_params["system"] = system
            if temperature is not None:
                api_params["temperature"] = temperature
            if top_p is not None:
                api_params["top_p"] = top_p
            if top_k is not None:
                api_params["top_k"] = top_k
            if enabled_tools:
                api_params["tools"] = [
                    AVAILABLE_TOOLS[t] for t in enabled_tools
                ]

            parsed = await self._call_api_with_tool_loop(
                api_params=api_params,
                messages=conversation_messages,
                user_id=ctx.author.id,
            )
            response_text = parsed.text
            thinking_text = parsed.thinking

            self.logger.debug(
                f"Received response from Claude: {response_text[:200]}..."
            )

            # Update initial response description based on input parameters
            truncated_prompt = truncate_text(prompt, 2000)
            description = f"**Prompt:** {truncated_prompt}\n"
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

            # Assemble all embeds for a single message
            embeds = [
                Embed(
                    title="Conversation Started",
                    description=description,
                    color=Colour.green(),
                )
            ]
            append_thinking_embeds(embeds, thinking_text)
            append_response_embeds(embeds, response_text)
            append_citations_embed(embeds, parsed.citations)
            append_stop_reason_embed(embeds, parsed.stop_reason)
            if SHOW_COST_EMBEDS:
                daily_cost = self._track_daily_cost(
                    ctx.author.id, model, parsed.input_tokens, parsed.output_tokens
                )
                append_pricing_embed(
                    embeds, model, parsed.input_tokens, parsed.output_tokens, daily_cost
                )

            if len(embeds) == 1:
                await ctx.send_followup("No response generated.")
                return

            # Create the view with buttons and tool select menu
            main_conversation_id = ctx.interaction.id
            view = ButtonView(
                cog=self,
                conversation_starter=ctx.author,
                conversation_id=main_conversation_id,
                initial_tools=enabled_tools,
            )
            self.views[ctx.author] = view

            # Send all embeds as a single message with buttons
            message = await ctx.send_followup(embeds=embeds, view=view)
            self.message_to_conversation_id[message.id] = main_conversation_id

            # Store the conversation details
            # conversation_messages already contains all turns from the tool loop
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
                conversation_id=main_conversation_id,
                tools=enabled_tools,
            )
            conversation = Conversation(
                params=params, messages=conversation_messages
            )
            self.conversations[main_conversation_id] = conversation

        except Exception as e:
            description = format_anthropic_error(e)
            self.logger.error(
                f"Error in chat: {description}",
                exc_info=True,
            )
            await ctx.send_followup(
                embed=Embed(title="Error", description=description, color=Colour.red())
            )

        finally:
            if typing_task:
                typing_task.cancel()
