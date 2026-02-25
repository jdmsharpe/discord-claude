import logging
from typing import cast

from discord import (
    ButtonStyle,
    Interaction,
    Member,
    SelectOption,
    TextChannel,
    User,
)
from discord.ui import Button, Select, View, button

from util import AVAILABLE_TOOLS


class ButtonView(View):
    def __init__(
        self,
        cog: "AnthropicAPI",
        conversation_starter: Member | User,
        conversation_id: int,
        initial_tools: list[str] | None = None,
    ):
        """
        Initialize the ButtonView class.
        """
        super().__init__(timeout=None)
        self.cog = cog
        self.conversation_starter = conversation_starter
        self.conversation_id = conversation_id
        self._add_tool_select(initial_tools)

    def _add_tool_select(self, initial_tools: list[str] | None = None) -> None:
        """Add a Select Menu for toggling tools mid-conversation."""
        selected_tools = set(initial_tools or [])

        tool_select = Select(
            placeholder="Tools",
            options=[
                SelectOption(
                    label="Web Search",
                    value="web_search",
                    description="Search the web for current information.",
                    default="web_search" in selected_tools,
                ),
                SelectOption(
                    label="Web Fetch",
                    value="web_fetch",
                    description="Fetch full content from web pages.",
                    default="web_fetch" in selected_tools,
                ),
                SelectOption(
                    label="Code Execution",
                    value="code_execution",
                    description="Run code in a sandbox.",
                    default="code_execution" in selected_tools,
                ),
                SelectOption(
                    label="Memory",
                    value="memory",
                    description="Save and recall memories across conversations.",
                    default="memory" in selected_tools,
                ),
            ],
            min_values=0,
            max_values=4,
            row=1,
        )

        async def _tool_callback(interaction: Interaction) -> None:
            await self.tool_select_callback(interaction, tool_select)

        tool_select.callback = _tool_callback
        self.add_item(tool_select)

    async def tool_select_callback(
        self, interaction: Interaction, tool_select: Select
    ) -> None:
        """Handle tool selection changes."""
        if interaction.user != self.conversation_starter:
            await interaction.response.send_message(
                "You are not allowed to change tools for this conversation.",
                ephemeral=True,
            )
            return

        conversation = self.cog.conversations.get(self.conversation_id)
        if conversation is None:
            await interaction.response.send_message(
                "No active conversation found.", ephemeral=True
            )
            return

        selected_values = [
            value for value in tool_select.values if value in AVAILABLE_TOOLS
        ]
        conversation.params.tools = selected_values

        status = ", ".join(selected_values) if selected_values else "none"
        await interaction.response.send_message(
            f"Tools updated: {status}.",
            ephemeral=True,
            delete_after=3,
        )

    @button(emoji="🔄", style=ButtonStyle.green, row=0)
    async def regenerate_button(self, _: Button, interaction: Interaction):
        """
        Regenerate the last response for the current conversation.

        Args:
            interaction (Interaction): The interaction object.
        """
        logging.info("Regenerate button clicked.")
        removed_entries = []

        try:
            if interaction.user != self.conversation_starter:
                await interaction.response.send_message(
                    "You are not allowed to regenerate the response.", ephemeral=True
                )
                return

            conversation = self.cog.conversations.get(self.conversation_id)
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
                (
                    message
                    for message in messages
                    if message.author == self.conversation_starter
                ),
                None,
            )

            if user_message is None:
                conversation.messages.extend(removed_entries)
                await interaction.followup.send(
                    "Couldn't find the message to regenerate.", ephemeral=True
                )
                return

            await self.cog.handle_new_message_in_conversation(
                user_message, conversation
            )
            await interaction.followup.send(
                "Response regenerated.", ephemeral=True, delete_after=3
            )
        except Exception as error:
            logging.error(
                f"Error in regenerate_button: {error}",
                exc_info=True,
            )

            if removed_entries:
                conversation = self.cog.conversations.get(self.conversation_id)
                if conversation is not None:
                    conversation.messages.extend(removed_entries)

            if interaction.response.is_done():
                await interaction.followup.send(
                    "An error occurred while regenerating the response.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "An error occurred while regenerating the response.", ephemeral=True
                )

    @button(emoji="⏯️", style=ButtonStyle.gray, row=0)
    async def play_pause_button(self, _: Button, interaction: Interaction):
        """
        Pause or resume the conversation.

        Args:
            interaction (Interaction): The interaction object.
        """
        # Check if the interaction user is the one who started the conversation
        if interaction.user != self.conversation_starter:
            await interaction.response.send_message(
                "You are not allowed to pause the conversation.", ephemeral=True
            )
            return

        # Toggle the paused state
        if self.conversation_id in self.cog.conversations:
            conversation = self.cog.conversations[self.conversation_id]
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

    @button(emoji="⏹️", style=ButtonStyle.blurple, row=0)
    async def stop_button(self, button: Button, interaction: Interaction):
        """
        End the conversation.

        Args:
            interaction (Interaction): The interaction object.
        """
        # Check if the interaction user is the one who started the conversation
        if interaction.user != self.conversation_starter:
            await interaction.response.send_message(
                "You are not allowed to end this conversation.", ephemeral=True
            )
            return

        # End the conversation
        if self.conversation_id in self.cog.conversations:
            del self.cog.conversations[self.conversation_id]
            button.disabled = True
            await interaction.response.send_message(
                "Conversation ended.", ephemeral=True, delete_after=3
            )
        else:
            await interaction.response.send_message(
                "No active conversation found.", ephemeral=True
            )
