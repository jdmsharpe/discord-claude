from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAnthropicAPIIntegration:
    """Integration tests for the Anthropic API client (mocked)."""

    @pytest.mark.asyncio
    async def test_messages_create_basic(self, mock_anthropic_client):
        """Test basic message creation with the Anthropic API."""
        response = await mock_anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello, Claude!"}],
        )

        assert response.content[0].text == "Hello! How can I help you today?"
        assert response.id.startswith("msg_")
        mock_anthropic_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_messages_create_with_system(self, mock_anthropic_client):
        """Test message creation with system prompt."""
        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system="You are a helpful assistant.",
            messages=[{"role": "user", "content": "What is 2+2?"}],
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a helpful assistant."

    @pytest.mark.asyncio
    async def test_messages_create_with_temperature(self, mock_anthropic_client):
        """Test message creation with temperature parameter."""
        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            temperature=0.7,
            messages=[{"role": "user", "content": "Be creative!"}],
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_messages_create_multi_turn(self, mock_anthropic_client):
        """Test multi-turn conversation."""
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=messages,
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert len(call_kwargs["messages"]) == 3

    @pytest.mark.asyncio
    async def test_messages_create_with_image_content(self, mock_anthropic_client):
        """Test message creation with image content block."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                        },
                    },
                    {"type": "text", "text": "What's in this image?"},
                ],
            }
        ]

        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=messages,
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["messages"][0]["content"][0]["type"] == "image"
        assert call_kwargs["messages"][0]["content"][1]["type"] == "text"


class TestAnthropicAPICog:
    """Tests for the AnthropicAPI Discord cog."""

    @pytest.fixture
    def cog(self, mock_bot):
        """Create an AnthropicAPI cog instance with mocked dependencies."""
        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            # Set up mock client
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Test response")]
            mock_response.id = "msg_test123"
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Import and create cog
            from src.anthropic_api import AnthropicAPI

            cog = AnthropicAPI(bot=mock_bot)
            cog.client = mock_client
            return cog

    @pytest.mark.asyncio
    async def test_cog_initialization(self, cog, mock_bot):
        """Test that the cog initializes correctly."""
        assert cog.bot == mock_bot
        assert cog.conversations == {}
        assert cog.views == {}

    @pytest.mark.asyncio
    async def test_converse_creates_conversation(
        self, cog, mock_discord_context, mock_anthropic_client
    ):
        """Test that converse command creates a conversation entry."""
        cog.client = mock_anthropic_client

        # Mock the channel typing context manager
        mock_discord_context.channel.typing = MagicMock()
        mock_discord_context.channel.typing.return_value.__aenter__ = AsyncMock()
        mock_discord_context.channel.typing.return_value.__aexit__ = AsyncMock()

        # Call the callback directly (bypassing the command decorator)
        await cog.converse.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello Claude!",
            model="claude-sonnet-4-20250514",
        )

        # Verify API was called
        mock_anthropic_client.messages.create.assert_called_once()

        # Verify conversation was stored
        assert len(cog.conversations) == 1

    @pytest.mark.asyncio
    async def test_converse_prevents_duplicate_conversations(
        self, cog, mock_discord_context
    ):
        """Test that users can't start multiple conversations in the same channel."""
        # Pre-populate with existing conversation
        from src.util import ChatCompletionParameters, Conversation

        existing_params = ChatCompletionParameters(
            model="claude-sonnet-4-20250514",
            conversation_starter=mock_discord_context.author,
            channel_id=mock_discord_context.channel.id,
            conversation_id=123,
        )
        cog.conversations[123] = Conversation(params=existing_params, messages=[])

        # Call the callback directly (bypassing the command decorator)
        await cog.converse.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello again!",
        )

        # Should have sent error message
        mock_discord_context.send_followup.assert_called()
        call_kwargs = mock_discord_context.send_followup.call_args[1]
        assert "already have an active conversation" in call_kwargs["embed"].description

    @pytest.mark.asyncio
    async def test_on_message_ignores_bot_messages(self, cog, mock_discord_message):
        """Test that the bot ignores its own messages."""
        mock_discord_message.author = cog.bot.user

        await cog.on_message(mock_discord_message)

        # Should not process the message (no API calls, no replies)
        mock_discord_message.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_keep_typing_can_be_cancelled(self, cog, mock_discord_context):
        """Test that the typing indicator can be cancelled."""
        import asyncio

        # Create a proper async context manager mock
        typing_cm = MagicMock()
        typing_cm.__aenter__ = AsyncMock(return_value=None)
        typing_cm.__aexit__ = AsyncMock(return_value=None)
        mock_discord_context.channel.typing = MagicMock(return_value=typing_cm)

        task = asyncio.create_task(cog.keep_typing(mock_discord_context.channel))

        # Give it a moment to start, then cancel immediately
        await asyncio.sleep(0.01)
        task.cancel()

        # Should raise CancelledError when awaited
        with pytest.raises(asyncio.CancelledError):
            await task
