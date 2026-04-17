from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import Future as ConcurrentFuture
from typing import Any, cast

from discord import (
    ButtonStyle,
    Interaction,
    Member,
    SelectOption,
    TextChannel,
    User,
)
from discord.ui import Button, Select, View, button

from discord_claude.util import ConversationKey, ToolChoice

from .tool_registry import TOOL_REGISTRY, get_tool_select_options


async def _send_interaction_error(interaction: Interaction, context: str, error: Exception) -> None:
    """Log an error and send the user a safe ephemeral message."""
    logging.error(f"Error in {context}: {error}", exc_info=True)
    msg = f"An error occurred while {context}."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


async def _build_view_on_running_loop(view: View, *, timeout: float | None) -> None:
    View.__init__(view, timeout=timeout)


def _initialize_view(view: View, *, timeout: float | None) -> None:
    """Build a discord View even when tests construct it outside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_build_view_on_running_loop(view, timeout=timeout))
        finally:
            loop.close()
        stopped_future: ConcurrentFuture[bool] = ConcurrentFuture()
        view._stopped = cast(Any, stopped_future)
    else:
        View.__init__(view, timeout=timeout)


class ButtonView(View):
    def __init__(
        self,
        *,
        conversation_starter: Member | User,
        conversation_key: ConversationKey,
        initial_tools: list[str] | None = None,
        initial_tool_choice: ToolChoice | None = None,
        get_conversation: Callable[[ConversationKey], Any | None],
        on_regenerate: Callable[[Any, Any], Awaitable[None]],
        on_stop: Callable[[ConversationKey, Member | User], Awaitable[None]],
    ):
        """
        Initialize the ButtonView class.
        """
        _initialize_view(self, timeout=None)
        self.conversation_starter = conversation_starter
        self.conversation_key = conversation_key
        self._get_conversation = get_conversation
        self._on_regenerate = on_regenerate
        self._on_stop = on_stop
        self._add_tool_select(initial_tools, initial_tool_choice)

    async def wait(self) -> bool:
        """Support wait() even when the view was constructed outside a running loop."""
        if isinstance(self._stopped, ConcurrentFuture):
            return await asyncio.wrap_future(self._stopped)
        return await super().wait()

    def _add_tool_select(
        self,
        initial_tools: list[str] | None = None,
        initial_tool_choice: ToolChoice | None = None,
    ) -> None:
        """Add a Select Menu for toggling tools mid-conversation."""
        selected_tools = set()
        if initial_tool_choice is None or initial_tool_choice["type"] != "none":
            selected_tools = set(initial_tools or [])

        tool_select = Select(
            placeholder="Tools",
            options=[SelectOption(**option) for option in get_tool_select_options(selected_tools)],
            min_values=0,
            max_values=len(TOOL_REGISTRY),
            row=1,
        )

        async def _tool_callback(interaction: Interaction) -> None:
            await self.tool_select_callback(interaction, tool_select)

        tool_select.callback = _tool_callback
        self.add_item(tool_select)

    async def tool_select_callback(self, interaction: Interaction, tool_select: Select) -> None:
        """Handle tool selection changes."""
        try:
            if interaction.user != self.conversation_starter:
                await interaction.response.send_message(
                    "You are not allowed to change tools for this conversation.",
                    ephemeral=True,
                )
                return

            conversation = self._get_conversation(self.conversation_key)
            if conversation is None:
                await interaction.response.send_message(
                    "No active conversation found.", ephemeral=True
                )
                return

            selected_values = [value for value in tool_select.values if value in TOOL_REGISTRY]
            if selected_values:
                conversation.params.tools = selected_values
                conversation.params.tool_choice = {"type": "auto"}
            else:
                conversation.params.tools = []
                advisor_model = getattr(conversation.params, "advisor_model", None)
                has_advisor = isinstance(advisor_model, str) and bool(advisor_model.strip())
                if getattr(conversation.params, "mcp_preset_names", []) or has_advisor:
                    conversation.params.tool_choice = {"type": "auto"}
                else:
                    conversation.params.tool_choice = {"type": "none"}

            # Update Select dropdown defaults
            selected_set = set(selected_values)
            for child in self.children:
                if isinstance(child, Select):
                    for option in child.options:
                        option.default = option.value in selected_set
                    break

            status = ", ".join(selected_values) if selected_values else "none"
            tool_behavior = conversation.params.tool_choice["type"]
            await interaction.response.send_message(
                f"Tools updated: {status}. Tool behavior: {tool_behavior}.",
                ephemeral=True,
                delete_after=3,
            )
        except Exception as e:
            await _send_interaction_error(interaction, "updating tools", e)

    @button(emoji="🔄", style=ButtonStyle.green, row=0)
    async def regenerate_button(self, _: Button, interaction: Interaction):
        """
        Regenerate the last response for the current conversation.

        Args:
            interaction (Interaction): The interaction object.
        """
        logging.info("Regenerate button clicked.")
        removed_entries: list[Any] = []

        try:
            if interaction.user != self.conversation_starter:
                await interaction.response.send_message(
                    "You are not allowed to regenerate the response.", ephemeral=True
                )
                return

            conversation = self._get_conversation(self.conversation_key)
            if conversation is None:
                await interaction.response.send_message(
                    "No active conversation found.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)

            if len(conversation.messages) < 2:
                await interaction.followup.send(
                    "Not enough history to regenerate yet.", ephemeral=True
                )
                return

            removed_entries = conversation.messages[-2:]
            del conversation.messages[-2:]

            channel = interaction.channel
            if not hasattr(channel, "history"):
                conversation.messages.extend(removed_entries)
                await interaction.followup.send(
                    "Couldn't find the message to regenerate.", ephemeral=True
                )
                return

            # Type narrowing: hasattr check above ensures channel has history()
            text_channel = cast(TextChannel, channel)
            messages = [message async for message in text_channel.history(limit=10)]
            user_message = next(
                (message for message in messages if message.author == self.conversation_starter),
                None,
            )

            if user_message is None:
                conversation.messages.extend(removed_entries)
                await interaction.followup.send(
                    "Couldn't find the message to regenerate.", ephemeral=True
                )
                return

            await self._on_regenerate(user_message, conversation)
            await interaction.followup.send("Response regenerated.", ephemeral=True, delete_after=3)
        except Exception as error:
            logging.error(
                f"Error in regenerate_button: {error}",
                exc_info=True,
            )

            if removed_entries:
                conversation = self._get_conversation(self.conversation_key)
                if conversation is not None:
                    conversation.messages.extend(removed_entries)

            if interaction.response.is_done():
                await interaction.followup.send(
                    "An error occurred while regenerating the response.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "An error occurred while regenerating the response.",
                    ephemeral=True,
                )

    @button(emoji="⏯️", style=ButtonStyle.gray, row=0)
    async def play_pause_button(self, _: Button, interaction: Interaction):
        """
        Pause or resume the conversation.

        Args:
            interaction (Interaction): The interaction object.
        """
        try:
            if interaction.user != self.conversation_starter:
                await interaction.response.send_message(
                    "You are not allowed to pause the conversation.", ephemeral=True
                )
                return

            conversation = self._get_conversation(self.conversation_key)
            if conversation is not None:
                conversation.params.paused = not conversation.params.paused
                status = "paused" if conversation.params.paused else "resumed"
                await interaction.response.send_message(
                    f"Conversation {status}. Press again to toggle.",
                    ephemeral=True,
                    delete_after=3,
                )
            else:
                await interaction.response.send_message(
                    "No active conversation found.", ephemeral=True
                )
        except Exception as e:
            await _send_interaction_error(interaction, "toggling pause", e)

    @button(emoji="⏹️", style=ButtonStyle.blurple, row=0)
    async def stop_button(self, button: Button, interaction: Interaction):
        """
        End the conversation.

        Args:
            interaction (Interaction): The interaction object.
        """
        try:
            if interaction.user != self.conversation_starter:
                await interaction.response.send_message(
                    "You are not allowed to end this conversation.", ephemeral=True
                )
                return

            conversation = self._get_conversation(self.conversation_key)
            if conversation is not None:
                await self._on_stop(self.conversation_key, self.conversation_starter)
                await interaction.response.send_message(
                    "Conversation ended.", ephemeral=True, delete_after=3
                )
            else:
                await interaction.response.send_message(
                    "No active conversation found.", ephemeral=True
                )
        except Exception as e:
            await _send_interaction_error(interaction, "ending the conversation", e)
