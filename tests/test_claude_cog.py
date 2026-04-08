import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_claude.cogs.claude.command_options import (
    CHAT_MODEL_CHOICES,
    RESPONSE_EFFORT_CHOICES,
    TOOL_CHOICE_CHOICES,
)


def _make_usage(**kwargs):
    """Create a mock usage object with proper numeric values and server_tool_use=None."""
    defaults = {
        "input_tokens": 10,
        "output_tokens": 15,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "server_tool_use": None,
    }
    defaults.update(kwargs)
    return MagicMock(**defaults)


class TestClaudeCog:
    """Tests for the Claude Discord cog."""

    @pytest.fixture
    def cog(self, mock_bot):
        """Create a ClaudeCog instance with mocked dependencies."""
        with patch("discord_claude.cogs.claude.client.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            text_block = MagicMock()
            text_block.type = "text"
            text_block.text = "Test response"
            text_block.citations = None
            mock_response.content = [text_block]
            mock_response.id = "msg_test123"
            mock_response.stop_reason = "end_turn"
            mock_response.usage = _make_usage()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            from discord_claude.cogs.claude.cog import ClaudeCog

            cog = ClaudeCog(bot=mock_bot)
            cog.client = mock_client
            return cog

    async def test_cog_initialization(self, cog, mock_bot):
        """Test that the cog initializes correctly."""
        assert cog.bot == mock_bot
        assert cog.conversations == {}
        assert cog.views == {}
        assert cog.last_view_messages == {}

    async def test_strip_previous_view_removes_buttons(self, cog):
        """_strip_previous_view edits the old message to remove its view."""
        user = MagicMock()
        old_message = AsyncMock()
        cog.last_view_messages[user] = old_message

        await cog._strip_previous_view(user)

        old_message.edit.assert_awaited_once_with(view=None)
        assert user not in cog.last_view_messages

    async def test_strip_previous_view_no_previous(self, cog):
        """_strip_previous_view is a no-op when there's no previous message."""
        user = MagicMock()
        await cog._strip_previous_view(user)
        assert user not in cog.last_view_messages

    async def test_strip_previous_view_handles_edit_error(self, cog):
        """_strip_previous_view swallows errors when the old message can't be edited."""
        user = MagicMock()
        old_message = AsyncMock()
        old_message.edit.side_effect = Exception("Message deleted")
        cog.last_view_messages[user] = old_message

        await cog._strip_previous_view(user)

        assert user not in cog.last_view_messages

    async def test_cleanup_conversation_strips_view_and_removes_state(self, cog):
        """_cleanup_conversation strips the view and removes it from self.views."""
        user = MagicMock()
        old_message = AsyncMock()
        cog.last_view_messages[user] = old_message
        cog.views[user] = MagicMock()

        await cog._cleanup_conversation(user)

        old_message.edit.assert_awaited_once_with(view=None)
        assert user not in cog.last_view_messages
        assert user not in cog.views

    async def test_cleanup_conversation_no_prior_state(self, cog):
        """_cleanup_conversation is a no-op when there's no prior state."""
        user = MagicMock()
        await cog._cleanup_conversation(user)
        assert user not in cog.last_view_messages
        assert user not in cog.views

    async def test_chat_creates_conversation(
        self, cog, mock_discord_context, mock_anthropic_client
    ):
        """Test that chat command creates a conversation entry."""
        cog.client = mock_anthropic_client

        mock_discord_context.channel.typing = MagicMock()
        mock_discord_context.channel.typing.return_value.__aenter__ = AsyncMock()
        mock_discord_context.channel.typing.return_value.__aexit__ = AsyncMock()

        await cog.chat.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello Claude!",
            model="claude-sonnet-4",
        )

        mock_anthropic_client.messages.create.assert_called_once()
        assert len(cog.conversations) == 1

    async def test_chat_prevents_duplicate_conversations(self, cog, mock_discord_context):
        """Test that users can't start multiple conversations in the same channel."""
        from discord_claude.util import ChatCompletionParameters, Conversation

        existing_params = ChatCompletionParameters(
            model="claude-sonnet-4",
            conversation_starter=mock_discord_context.author,
            channel_id=mock_discord_context.channel.id,
            conversation_id=123,
        )
        conv_key = (mock_discord_context.author.id, mock_discord_context.channel.id)
        cog.conversations[conv_key] = Conversation(params=existing_params, messages=[])

        await cog.chat.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello again!",
        )

        mock_discord_context.send_followup.assert_called()
        call_kwargs = mock_discord_context.send_followup.call_args[1]
        assert "already have an active conversation" in call_kwargs["embed"].description

    async def test_on_message_ignores_bot_messages(self, cog, mock_discord_message):
        """Test that the bot ignores its own messages."""
        mock_discord_message.author = cog.bot.user

        await cog.on_message(mock_discord_message)

        mock_discord_message.reply.assert_not_called()

    async def test_keep_typing_can_be_cancelled(self, cog, mock_discord_context):
        """Test that the typing indicator can be cancelled."""
        typing_cm = MagicMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        mock_discord_context.channel.typing = MagicMock(return_value=typing_cm)

        task = asyncio.create_task(cog.keep_typing(mock_discord_context.channel))

        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_handle_new_message_rejects_invalid_tool_choice_before_api_call(
        self, cog, mock_discord_message
    ):
        """Invalid thinking/tool_choice combos fail fast without hitting Anthropic."""
        from discord_claude.util import ChatCompletionParameters, Conversation

        params = ChatCompletionParameters(
            model="claude-opus-4-6",
            conversation_starter=mock_discord_message.author,
            channel_id=mock_discord_message.channel.id,
            conversation_id=123,
            tools=["memory"],
            tool_choice={"type": "tool", "name": "memory"},
        )
        conversation = Conversation(params=params, messages=[])

        await cog.handle_new_message_in_conversation(mock_discord_message, conversation)

        cog.client.messages.create.assert_not_called()
        mock_discord_message.reply.assert_awaited_once()
        reply_embed = mock_discord_message.reply.call_args.kwargs["embed"]
        assert reply_embed.title == "Unsupported Tool Configuration"
        assert "Thinking mode only supports tool behavior `auto` or `none`" in (
            reply_embed.description
        )
        assert conversation.messages == []


def test_critical_choice_values_present():
    assert any(choice.value == "claude-opus-4-6" for choice in CHAT_MODEL_CHOICES)
    assert any(choice.value == "claude-mythos-preview" for choice in CHAT_MODEL_CHOICES)


def test_effort_choice_set():
    values = {choice.value for choice in RESPONSE_EFFORT_CHOICES}
    assert values == {"low", "medium", "high"}


def test_tool_choice_set():
    values = {choice.value for choice in TOOL_CHOICE_CHOICES}
    assert values == {"auto", "none"}
