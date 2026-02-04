# Standard library imports
import asyncio
import base64
import logging
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
from config.auth import ANTHROPIC_API_KEY, GUILD_IDS
from util import (
    ChatCompletionParameters,
    Conversation,
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
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(data).decode("utf-8"),
            },
        }
    elif content_type in SUPPORTED_DOCUMENT_TYPES or (
        content_type and content_type.startswith("text/")
    ):
        # For text files, decode and send as plain text document
        try:
            text_content = data.decode("utf-8")
        except UnicodeDecodeError:
            text_content = data.decode("latin-1")

        # Include filename context if available
        prefix = f"[File: {filename}]\n\n" if filename else ""
        return {
            "type": "text",
            "text": f"{prefix}{text_content}",
        }
    return None


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


class AnthropicAPI(commands.Cog):
    # Slash command group for all Anthropic commands: /anthropic <subcommand>
    anthropic = SlashCommandGroup(
        "anthropic", "Anthropic Claude commands", guild_ids=GUILD_IDS
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

        # Dictionary to store conversation state for each converse interaction
        self.conversations: dict[int, Conversation] = {}
        # Dictionary to map any message ID to the main conversation ID for tracking
        self.message_to_conversation_id: dict[int, int] = {}
        # Dictionary to store UI views for each conversation
        self.views = {}
        self._http_session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session and not self._http_session.closed:
            return self._http_session
        async with self._session_lock:
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()
            return self._http_session

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
            if params.system:
                api_params["system"] = params.system
            if params.temperature is not None:
                api_params["temperature"] = params.temperature
            if params.top_p is not None:
                api_params["top_p"] = params.top_p
            if params.top_k is not None:
                api_params["top_k"] = params.top_k

            response = await self.client.messages.create(**api_params)
            response_text = (
                response.content[0].text if response.content else "No response."
            )
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

            # Add assistant message to history
            messages.append({"role": "assistant", "content": response_text})

            append_response_embeds(embeds, response_text)

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

    @anthropic.command(
        name="converse",
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
        description="Choose from the following Claude models. (default: Claude Opus 4.5)",
        required=False,
        choices=[
            OptionChoice(name="Claude Opus 4.5", value="claude-opus-4-5-20251101"),
            OptionChoice(name="Claude Sonnet 4.5", value="claude-sonnet-4-5-20250514"),
            OptionChoice(name="Claude Sonnet 4", value="claude-sonnet-4-20250514"),
            OptionChoice(name="Claude Haiku 3.5", value="claude-haiku-3-5-20241022"),
            OptionChoice(name="Claude 3.5 Sonnet", value="claude-3-5-sonnet-20241022"),
            OptionChoice(name="Claude 3.5 Haiku", value="claude-3-5-haiku-20241022"),
            OptionChoice(name="Claude 3 Opus", value="claude-3-opus-20240229"),
            OptionChoice(name="Claude 3 Sonnet", value="claude-3-sonnet-20240229"),
            OptionChoice(name="Claude 3 Haiku", value="claude-3-haiku-20240307"),
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
    async def converse(
        self,
        ctx: ApplicationContext,
        prompt: str,
        model: str = "claude-opus-4-5-20251101",
        system: str | None = None,
        attachment: Attachment | None = None,
        max_tokens: int = 16384,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
    ):
        """
        Creates a persistent conversation session with Claude.

        Initiates an interactive conversation with context preservation across multiple exchanges.
        Supports multimodal inputs (text + images) and provides interactive UI controls for
        conversation management.

        Args:
            ctx: Discord application context
            prompt: Initial conversation prompt or question
            model: Claude model variant (default: claude-opus-4-5-20251101)
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

            # Build API call parameters
            api_params: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": user_content}],
            }
            if system:
                api_params["system"] = system
            if temperature is not None:
                api_params["temperature"] = temperature
            if top_p is not None:
                api_params["top_p"] = top_p
            if top_k is not None:
                api_params["top_k"] = top_k

            response = await self.client.messages.create(**api_params)
            response_text = (
                response.content[0].text if response.content else "No response."
            )

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

            # Assemble all embeds for a single message
            embeds = [
                Embed(
                    title="Conversation Started",
                    description=description,
                    color=Colour.green(),
                )
            ]
            append_response_embeds(embeds, response_text)

            if len(embeds) == 1:
                await ctx.send_followup("No response generated.")
                return

            # Create the view with buttons
            main_conversation_id = ctx.interaction.id
            view = ButtonView(
                cog=self,
                conversation_starter=ctx.author,
                conversation_id=main_conversation_id,
            )
            self.views[ctx.author] = view

            # Send all embeds as a single message with buttons
            message = await ctx.send_followup(embeds=embeds, view=view)
            self.message_to_conversation_id[message.id] = main_conversation_id

            # Store the conversation details
            params = ChatCompletionParameters(
                model=model,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                conversation_starter=ctx.author,
                channel_id=ctx.channel.id,
                conversation_id=main_conversation_id,
            )
            messages = [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": response_text},
            ]
            conversation = Conversation(params=params, messages=messages)
            self.conversations[main_conversation_id] = conversation

        except Exception as e:
            description = format_anthropic_error(e)
            self.logger.error(
                f"Error in converse: {description}",
                exc_info=True,
            )
            await ctx.send_followup(
                embed=Embed(title="Error", description=description, color=Colour.red())
            )

        finally:
            if typing_task:
                typing_task.cancel()

    @anthropic.command(
        name="check_permissions",
        description="Check if bot has necessary permissions in this channel",
    )
    async def check_permissions(self, ctx: ApplicationContext):
        if ctx.guild is None or ctx.channel is None:
            await ctx.respond("This command can only be used in a guild channel.")
            return

        permissions_for = getattr(ctx.channel, "permissions_for", None)
        if permissions_for is None:
            await ctx.respond("Cannot check permissions for this channel type.")
            return

        permissions = permissions_for(ctx.guild.me)
        if permissions.read_messages and permissions.read_message_history:
            await ctx.respond(
                "Bot has permission to read messages and message history."
            )
        else:
            await ctx.respond("Bot is missing necessary permissions in this channel.")
