from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExtractResponseContent:
    """Tests for the extract_response_content helper."""

    def test_text_only(self):
        """Response with only text blocks."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "Hello!"
        assert parsed.thinking == ""
        assert parsed.citations == []
        assert parsed.has_tool_use is False

    def test_thinking_and_text(self):
        """Response with thinking and text blocks."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "Let me reason about this..."
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "The answer is 42."
        text_block.citations = None
        response.content = [thinking_block, text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "The answer is 42."
        assert parsed.thinking == "Let me reason about this..."

    def test_redacted_thinking_ignored(self):
        """Redacted thinking blocks should be skipped."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        redacted_block = MagicMock()
        redacted_block.type = "redacted_thinking"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        response.content = [redacted_block, text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "Response."
        assert parsed.thinking == ""

    def test_empty_content(self):
        """Response with no content blocks."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        response.content = []

        parsed = extract_response_content(response)
        assert parsed.text == "No response."
        assert parsed.thinking == ""

    def test_with_web_citations(self):
        """Response with text blocks containing web search citations."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "According to sources..."
        citation1 = MagicMock()
        citation1.url = "https://example.com/1"
        citation1.title = "Source 1"
        citation1.cited_text = "cited text 1"
        citation2 = MagicMock()
        citation2.url = "https://example.com/2"
        citation2.title = "Source 2"
        citation2.cited_text = "cited text 2"
        text_block.citations = [citation1, citation2]
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert len(parsed.citations) == 2
        assert parsed.citations[0]["kind"] == "web"
        assert parsed.citations[0]["url"] == "https://example.com/1"
        assert parsed.citations[1]["title"] == "Source 2"

    def test_with_document_citations(self):
        """Response with document citations (char_location, page_location)."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "The document says..."

        char_citation = MagicMock()
        char_citation.url = None
        char_citation.type = "char_location"
        char_citation.cited_text = "The grass is green."
        char_citation.document_title = "My Document"
        char_citation.document_index = 0
        char_citation.start_char_index = 0
        char_citation.end_char_index = 19

        page_citation = MagicMock()
        page_citation.url = None
        page_citation.type = "page_location"
        page_citation.cited_text = "Water is essential."
        page_citation.document_title = "PDF Report"
        page_citation.document_index = 1
        page_citation.start_page_number = 5
        page_citation.end_page_number = 6

        text_block.citations = [char_citation, page_citation]
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert len(parsed.citations) == 2
        assert parsed.citations[0]["kind"] == "document"
        assert parsed.citations[0]["cited_text"] == "The grass is green."
        assert parsed.citations[0]["document_title"] == "My Document"
        assert parsed.citations[0]["location"] == ""
        assert parsed.citations[1]["kind"] == "document"
        assert parsed.citations[1]["cited_text"] == "Water is essential."
        assert parsed.citations[1]["location"] == "p. 5"

    def test_document_citations_multi_page(self):
        """Page citations spanning multiple pages show page range."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Spanning pages..."
        citation = MagicMock()
        citation.url = None
        citation.type = "page_location"
        citation.cited_text = "A long passage."
        citation.document_title = "Report"
        citation.start_page_number = 3
        citation.end_page_number = 6
        text_block.citations = [citation]
        response.content = [text_block]

        parsed = extract_response_content(response)
        assert parsed.citations[0]["location"] == "pp. 3\u20135"

    def test_document_citations_deduplicated(self):
        """Duplicate document cited_text values are deduplicated."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        block1 = MagicMock()
        block1.type = "text"
        block1.text = "Part 1"
        cite1 = MagicMock()
        cite1.url = None
        cite1.type = "char_location"
        cite1.cited_text = "Same passage."
        cite1.document_title = "Doc"
        block1.citations = [cite1]

        block2 = MagicMock()
        block2.type = "text"
        block2.text = "Part 2"
        cite2 = MagicMock()
        cite2.url = None
        cite2.type = "char_location"
        cite2.cited_text = "Same passage."
        cite2.document_title = "Doc"
        block2.citations = [cite2]

        response.content = [block1, block2]
        parsed = extract_response_content(response)
        assert len(parsed.citations) == 1

    def test_web_citations_deduplicated(self):
        """Duplicate web citation URLs are deduplicated."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        text_block1 = MagicMock()
        text_block1.type = "text"
        text_block1.text = "Part 1"
        citation1 = MagicMock()
        citation1.url = "https://example.com/same"
        citation1.title = "Same Source"
        citation1.cited_text = "text"
        text_block1.citations = [citation1]

        text_block2 = MagicMock()
        text_block2.type = "text"
        text_block2.text = "Part 2"
        citation2 = MagicMock()
        citation2.url = "https://example.com/same"
        citation2.title = "Same Source Again"
        citation2.cited_text = "text"
        text_block2.citations = [citation2]

        response.content = [text_block1, text_block2]

        parsed = extract_response_content(response)
        assert len(parsed.citations) == 1

    def test_tool_use_detected(self):
        """Response with tool_use block is detected."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Let me check."
        text_block.citations = None
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "memory"
        tool_block.input = {"command": "view"}
        response.content = [text_block, tool_block]

        parsed = extract_response_content(response)
        assert parsed.has_tool_use is True
        assert len(parsed.tool_use_blocks) == 1
        assert parsed.tool_use_blocks[0].name == "memory"

    def test_server_tool_blocks_skipped(self):
        """Server-side tool blocks don't appear in text but raw_content preserves them."""
        from src.anthropic_api import extract_response_content

        response = MagicMock()
        server_block = MagicMock()
        server_block.type = "server_tool_use"
        result_block = MagicMock()
        result_block.type = "web_search_tool_result"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Here are the results."
        text_block.citations = None
        response.content = [server_block, result_block, text_block]

        parsed = extract_response_content(response)
        assert parsed.text == "Here are the results."
        assert parsed.has_tool_use is False
        assert len(parsed.raw_content) == 3


class TestAppendThinkingEmbeds:
    """Tests for the append_thinking_embeds helper."""

    def test_no_thinking(self):
        """Empty thinking text should not add an embed."""
        from src.anthropic_api import append_thinking_embeds

        embeds = []
        append_thinking_embeds(embeds, "")
        assert len(embeds) == 0

    def test_with_thinking(self):
        """Thinking text should be wrapped in spoiler tags."""
        from src.anthropic_api import append_thinking_embeds

        embeds = []
        append_thinking_embeds(embeds, "Some reasoning here")
        assert len(embeds) == 1
        assert embeds[0].title == "Thinking"
        assert embeds[0].description == "||Some reasoning here||"

    def test_long_thinking_truncated(self):
        """Long thinking text should be truncated."""
        from src.anthropic_api import append_thinking_embeds

        embeds = []
        long_text = "a" * 4000
        append_thinking_embeds(embeds, long_text)
        assert len(embeds) == 1
        assert len(embeds[0].description) < 3600
        assert "[thinking truncated]" in embeds[0].description


class TestAppendCitationsEmbed:
    """Tests for the append_citations_embed helper."""

    def test_no_citations(self):
        """Empty citations list adds no embed."""
        from src.anthropic_api import append_citations_embed

        embeds = []
        append_citations_embed(embeds, [])
        assert len(embeds) == 0

    def test_with_web_citations(self):
        """Web citations are rendered as a Sources embed with markdown links."""
        from src.anthropic_api import append_citations_embed

        embeds = []
        citations = [
            {"kind": "web", "url": "https://example.com/1", "title": "First Source"},
            {"kind": "web", "url": "https://example.com/2", "title": "Second Source"},
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert embeds[0].title == "Sources"
        assert "[First Source](https://example.com/1)" in embeds[0].description
        assert "[Second Source](https://example.com/2)" in embeds[0].description

    def test_web_citations_capped_at_20(self):
        """Only the first 20 web citations are included."""
        from src.anthropic_api import append_citations_embed

        embeds = []
        citations = [
            {"kind": "web", "url": f"https://example.com/{i}", "title": f"Source {i}"}
            for i in range(25)
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert "Source 19" in embeds[0].description
        assert "Source 20" not in embeds[0].description

    def test_with_document_citations(self):
        """Document citations are rendered as quoted text with source info."""
        from src.anthropic_api import append_citations_embed

        embeds = []
        citations = [
            {
                "kind": "document",
                "cited_text": "The grass is green.",
                "document_title": "Nature Doc",
                "location": "",
            },
            {
                "kind": "document",
                "cited_text": "Water is essential.",
                "document_title": "Science PDF",
                "location": "p. 5",
            },
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert "The grass is green." in embeds[0].description
        assert "Nature Doc" in embeds[0].description
        assert "Science PDF, p. 5" in embeds[0].description

    def test_mixed_web_and_document_citations(self):
        """Both web and document citations appear in the same embed."""
        from src.anthropic_api import append_citations_embed

        embeds = []
        citations = [
            {"kind": "web", "url": "https://example.com", "title": "Web Source"},
            {
                "kind": "document",
                "cited_text": "Document text.",
                "document_title": "My Doc",
                "location": "p. 2",
            },
        ]
        append_citations_embed(embeds, citations)
        assert len(embeds) == 1
        assert "[Web Source](https://example.com)" in embeds[0].description
        assert "Document text." in embeds[0].description


class TestAppendStopReasonEmbed:
    """Tests for the append_stop_reason_embed helper."""

    def test_end_turn_no_embed(self):
        """end_turn should not add any embed."""
        from src.anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "end_turn")
        assert len(embeds) == 0

    def test_max_tokens(self):
        """max_tokens should add a truncation warning."""
        from src.anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "max_tokens")
        assert len(embeds) == 1
        assert embeds[0].title == "Response Truncated"

    def test_model_context_window_exceeded(self):
        """model_context_window_exceeded should add a context limit warning."""
        from src.anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "model_context_window_exceeded")
        assert len(embeds) == 1
        assert embeds[0].title == "Context Limit Reached"

    def test_refusal(self):
        """refusal should add a declined warning."""
        from src.anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "refusal")
        assert len(embeds) == 1
        assert embeds[0].title == "Request Declined"

    def test_pause_turn_no_embed(self):
        """pause_turn should not add any embed."""
        from src.anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "pause_turn")
        assert len(embeds) == 0


class TestAnthropicAPIIntegration:
    """Integration tests for the Anthropic API client (mocked)."""

    @pytest.mark.asyncio
    async def test_messages_create_basic(self, mock_anthropic_client):
        """Test basic message creation with the Anthropic API."""
        response = await mock_anthropic_client.messages.create(
            model="claude-sonnet-4",
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
            model="claude-sonnet-4",
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
            model="claude-sonnet-4",
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
            model="claude-sonnet-4",
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
            model="claude-sonnet-4",
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
            text_block = MagicMock()
            text_block.type = "text"
            text_block.text = "Test response"
            text_block.citations = None
            mock_response.content = [text_block]
            mock_response.id = "msg_test123"
            mock_response.stop_reason = "end_turn"
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
    async def test_chat_creates_conversation(
        self, cog, mock_discord_context, mock_anthropic_client
    ):
        """Test that chat command creates a conversation entry."""
        cog.client = mock_anthropic_client

        # Mock the channel typing context manager
        mock_discord_context.channel.typing = MagicMock()
        mock_discord_context.channel.typing.return_value.__aenter__ = AsyncMock()
        mock_discord_context.channel.typing.return_value.__aexit__ = AsyncMock()

        # Call the callback directly (bypassing the command decorator)
        await cog.chat.callback(
            cog,
            ctx=mock_discord_context,
            prompt="Hello Claude!",
            model="claude-sonnet-4",
        )

        # Verify API was called
        mock_anthropic_client.messages.create.assert_called_once()

        # Verify conversation was stored
        assert len(cog.conversations) == 1

    @pytest.mark.asyncio
    async def test_chat_prevents_duplicate_conversations(
        self, cog, mock_discord_context
    ):
        """Test that users can't start multiple conversations in the same channel."""
        # Pre-populate with existing conversation
        from src.util import ChatCompletionParameters, Conversation

        existing_params = ChatCompletionParameters(
            model="claude-sonnet-4",
            conversation_starter=mock_discord_context.author,
            channel_id=mock_discord_context.channel.id,
            conversation_id=123,
        )
        cog.conversations[123] = Conversation(params=existing_params, messages=[])

        # Call the callback directly (bypassing the command decorator)
        await cog.chat.callback(
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


class TestCallApiWithToolLoop:
    """Tests for the _call_api_with_tool_loop method."""

    @pytest.fixture
    def cog(self, mock_bot):
        """Create an AnthropicAPI cog instance."""
        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from src.anthropic_api import AnthropicAPI

            cog = AnthropicAPI(bot=mock_bot)
            cog.client = mock_client
            return cog

    @pytest.mark.asyncio
    async def test_simple_end_turn(self, cog):
        """Single API call with end_turn returns ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        assert len(messages) == 2  # user + assistant
        assert messages[1]["role"] == "assistant"
        cog.client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_turn_continues(self, cog):
        """pause_turn response causes re-send, then end_turn completes."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Found it!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"

        cog.client.messages.create = AsyncMock(
            side_effect=[pause_response, final_response]
        )

        messages = [{"role": "user", "content": "Search for something"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Found it!"
        assert cog.client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_tool_use_loop(self, cog):
        """tool_use triggers execution and re-send."""
        # First response: tool_use
        tool_response = MagicMock()
        tool_text = MagicMock()
        tool_text.type = "text"
        tool_text.text = "Let me check."
        tool_text.citations = None
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_123"
        tool_block.name = "memory"
        tool_block.input = {"command": "view", "path": "/memories"}
        tool_response.content = [tool_text, tool_block]
        tool_response.stop_reason = "tool_use"

        # Second response: end_turn
        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "No memories found."
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"

        cog.client.messages.create = AsyncMock(
            side_effect=[tool_response, final_response]
        )

        messages = [{"role": "user", "content": "Check my memories"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        with patch("src.anthropic_api.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "No memory files found."

            parsed = await cog._call_api_with_tool_loop(
                api_params=api_params, messages=messages, user_id=123
            )

        assert parsed.text == "No memories found."
        assert cog.client.messages.create.call_count == 2
        # Messages should have: user, assistant (tool_use), user (tool_result), assistant (final)
        assert len(messages) == 4

    @pytest.mark.asyncio
    async def test_max_iterations_safety(self, cog):
        """Loop stops at max_iterations."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Still working..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"

        cog.client.messages.create = AsyncMock(return_value=pause_response)

        messages = [{"role": "user", "content": "Do something"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params,
            messages=messages,
            user_id=123,
            max_iterations=3,
        )

        assert cog.client.messages.create.call_count == 3

    @pytest.mark.asyncio
    async def test_max_tokens_stop_reason(self, cog):
        """max_tokens stop reason is propagated on ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Truncated response..."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "max_tokens"
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Write a long essay"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 10}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "max_tokens"
        assert parsed.text == "Truncated response..."
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_refusal_stop_reason(self, cog):
        """refusal stop reason is propagated on ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I can't help with that."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "refusal"
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Bad request"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "refusal"

    @pytest.mark.asyncio
    async def test_context_window_exceeded_stop_reason(self, cog):
        """model_context_window_exceeded stop reason is propagated."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Partial response..."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "model_context_window_exceeded"
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Very long conversation"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 64000}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "model_context_window_exceeded"

    @pytest.mark.asyncio
    async def test_compaction_model_uses_beta_api(self, cog):
        """Compaction models use client.beta.messages.create with compaction params."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-opus-4-6", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert call_kwargs["betas"] == ["compact-2026-01-12"]
        assert call_kwargs["context_management"] == {
            "edits": [{"type": "compact_20260112"}]
        }

    @pytest.mark.asyncio
    async def test_non_compaction_model_uses_regular_api(self, cog):
        """Non-compaction models use client.messages.create without compaction."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        cog.client.messages.create.assert_called_once()
