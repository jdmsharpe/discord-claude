from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


class TestExtractResponseContent:
    """Tests for the extract_response_content helper."""

    def test_text_only(self):
        """Response with only text blocks."""
        from anthropic_api import extract_response_content

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

    def test_thinking_and_text(self):
        """Response with thinking and text blocks."""
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

        response = MagicMock()
        response.content = []

        parsed = extract_response_content(response)
        assert parsed.text == "No response."
        assert parsed.thinking == ""

    def test_with_web_citations(self):
        """Response with text blocks containing web search citations."""
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

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
        from anthropic_api import extract_response_content

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
        assert len(parsed.tool_use_blocks) == 1
        assert parsed.tool_use_blocks[0].name == "memory"

    def test_server_tool_blocks_skipped(self):
        """Server-side tool blocks don't appear in text or tool_use_blocks."""
        from anthropic_api import extract_response_content

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
        assert len(parsed.tool_use_blocks) == 0


class TestAppendThinkingEmbeds:
    """Tests for the append_thinking_embeds helper."""

    def test_no_thinking(self):
        """Empty thinking text should not add an embed."""
        from anthropic_api import append_thinking_embeds

        embeds = []
        append_thinking_embeds(embeds, "")
        assert len(embeds) == 0

    def test_with_thinking(self):
        """Thinking text should be wrapped in spoiler tags."""
        from anthropic_api import append_thinking_embeds

        embeds = []
        append_thinking_embeds(embeds, "Some reasoning here")
        assert len(embeds) == 1
        assert embeds[0].title == "Thinking"
        assert embeds[0].description == "||Some reasoning here||"

    def test_long_thinking_truncated(self):
        """Long thinking text should be truncated."""
        from anthropic_api import append_thinking_embeds

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
        from anthropic_api import append_citations_embed

        embeds = []
        append_citations_embed(embeds, [])
        assert len(embeds) == 0

    def test_with_web_citations(self):
        """Web citations are rendered as a Sources embed with markdown links."""
        from anthropic_api import append_citations_embed

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
        from anthropic_api import append_citations_embed

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
        from anthropic_api import append_citations_embed

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
        from anthropic_api import append_citations_embed

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
        from anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "end_turn")
        assert len(embeds) == 0

    def test_max_tokens(self):
        """max_tokens should add a truncation warning."""
        from anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "max_tokens")
        assert len(embeds) == 1
        assert embeds[0].title == "Response Truncated"

    def test_model_context_window_exceeded(self):
        """model_context_window_exceeded should add a context limit warning."""
        from anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "model_context_window_exceeded")
        assert len(embeds) == 1
        assert embeds[0].title == "Context Limit Reached"

    def test_refusal(self):
        """refusal should add a declined warning."""
        from anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "refusal")
        assert len(embeds) == 1
        assert embeds[0].title == "Request Declined"

    def test_pause_turn_no_embed(self):
        """pause_turn should not add any embed."""
        from anthropic_api import append_stop_reason_embed

        embeds = []
        append_stop_reason_embed(embeds, "pause_turn")
        assert len(embeds) == 0


class TestAppendPricingEmbed:
    """Tests for the append_pricing_embed helper."""

    def _make_parsed(self, **kwargs):
        """Create a ParsedResponse with given token/tool counts."""
        from anthropic_api import ParsedResponse

        defaults = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_tokens": 0,
            "cache_read_tokens": 0,
            "web_search_requests": 0,
            "web_fetch_requests": 0,
            "code_execution_requests": 0,
        }
        defaults.update(kwargs)
        parsed = ParsedResponse()
        for k, v in defaults.items():
            setattr(parsed, k, v)
        return parsed

    def test_basic_pricing_embed(self):
        """Basic embed shows cost, token counts, and daily total."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(input_tokens=1000, output_tokens=500)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.50)
        assert len(embeds) == 1
        desc = embeds[0].description
        assert "1,000 tokens in" in desc
        assert "500 tokens out" in desc
        assert "daily $0.50" in desc

    def test_pricing_embed_with_cache_hits(self):
        """Cache hits are shown when present."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(cache_read_tokens=5000)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "5,000 cached" in embeds[0].description

    def test_pricing_embed_with_web_searches(self):
        """Web search count is shown when present."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(web_search_requests=3)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "3 searches" in embeds[0].description

    def test_pricing_embed_single_search_no_plural(self):
        """Single web search uses singular form."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(web_search_requests=1)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "1 search" in embeds[0].description
        assert "searches" not in embeds[0].description

    def test_pricing_embed_with_web_fetches(self):
        """Web fetch count is shown when present."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(web_fetch_requests=2)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "2 fetches" in embeds[0].description

    def test_pricing_embed_with_code_execution(self):
        """Code execution count is shown when present."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed(code_execution_requests=1)
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        assert "1 code exec" in embeds[0].description
        assert "execs" not in embeds[0].description

    def test_pricing_embed_no_server_tools_hidden(self):
        """Server tool counts are hidden when zero."""
        from anthropic_api import append_pricing_embed

        embeds = []
        parsed = self._make_parsed()
        append_pricing_embed(embeds, parsed, request_cost=0.01, daily_cost=0.10)
        desc = embeds[0].description
        assert "search" not in desc
        assert "fetch" not in desc
        assert "code exec" not in desc


class TestToolChoiceSupport:
    """Tests for tool_choice request handling and validation."""

    def test_build_api_params_omits_tool_choice_by_default(self):
        """tool_choice is omitted unless explicitly provided."""
        from anthropic_api import AnthropicAPI
        from util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-haiku-4-5", tools=["web_search"])

        api_params = AnthropicAPI._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert "tool_choice" not in api_params

    def test_build_api_params_includes_explicit_none(self):
        """Explicit none is forwarded to the Anthropic request."""
        from anthropic_api import AnthropicAPI
        from util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            tools=["web_search"],
            tool_choice={"type": "none"},
        )

        api_params = AnthropicAPI._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert api_params["tool_choice"] == {"type": "none"}
        assert api_params["tools"][0]["name"] == "web_search"

    def test_build_api_params_omits_tool_choice_when_no_tools(self):
        """tool_choice is not forwarded when no tools are enabled."""
        from anthropic_api import AnthropicAPI
        from util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            tools=[],
            tool_choice={"type": "auto"},
        )

        api_params = AnthropicAPI._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert "tool_choice" not in api_params
        assert "tools" not in api_params

    def test_validate_request_configuration_rejects_forced_any_with_thinking(self):
        """Thinking mode rejects forced any-tool selection."""
        from anthropic_api import AnthropicAPI
        from util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-opus-4-6",
            tools=["web_search"],
            tool_choice={"type": "any"},
        )

        error = AnthropicAPI._validate_request_configuration(params)

        assert error is not None
        assert "Thinking mode only supports tool behavior `auto` or `none`" in error

    def test_validate_request_configuration_rejects_forced_tool_with_thinking(self):
        """Thinking mode rejects a specific forced tool."""
        from anthropic_api import AnthropicAPI
        from util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            thinking_budget=5000,
            tools=["memory"],
            tool_choice={"type": "tool", "name": "memory"},
        )

        error = AnthropicAPI._validate_request_configuration(params)

        assert error is not None
        assert "Thinking mode only supports tool behavior `auto` or `none`" in error


class TestAnthropicAPIIntegration:
    """Integration tests for the Anthropic API client (mocked)."""

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
            mock_response.usage = _make_usage()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            # Import and create cog
            from anthropic_api import AnthropicAPI

            cog = AnthropicAPI(bot=mock_bot)
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

    async def test_chat_prevents_duplicate_conversations(self, cog, mock_discord_context):
        """Test that users can't start multiple conversations in the same channel."""
        # Pre-populate with existing conversation using (user_id, channel_id) key
        from util import ChatCompletionParameters, Conversation

        existing_params = ChatCompletionParameters(
            model="claude-sonnet-4",
            conversation_starter=mock_discord_context.author,
            channel_id=mock_discord_context.channel.id,
            conversation_id=123,
        )
        conv_key = (mock_discord_context.author.id, mock_discord_context.channel.id)
        cog.conversations[conv_key] = Conversation(params=existing_params, messages=[])

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

    async def test_on_message_ignores_bot_messages(self, cog, mock_discord_message):
        """Test that the bot ignores its own messages."""
        mock_discord_message.author = cog.bot.user

        await cog.on_message(mock_discord_message)

        # Should not process the message (no API calls, no replies)
        mock_discord_message.reply.assert_not_called()

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

    async def test_handle_new_message_rejects_invalid_tool_choice_before_api_call(
        self, cog, mock_discord_message
    ):
        """Invalid thinking/tool_choice combos fail fast without hitting Anthropic."""
        from util import ChatCompletionParameters, Conversation

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


class TestCallApiWithToolLoop:
    """Tests for the _call_api_with_tool_loop method."""

    @pytest.fixture
    def cog(self, mock_bot):
        """Create an AnthropicAPI cog instance."""
        with patch("anthropic.AsyncAnthropic") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            from anthropic_api import AnthropicAPI

            cog = AnthropicAPI(bot=mock_bot)
            cog.client = mock_client
            return cog

    async def test_simple_end_turn(self, cog):
        """Single API call with end_turn returns ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
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

    async def test_pause_turn_continues(self, cog):
        """pause_turn response causes re-send, then end_turn completes."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = None

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Found it!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None

        cog.client.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [{"role": "user", "content": "Search for something"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Found it!"
        assert cog.client.messages.create.call_count == 2

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
        tool_response.usage = None

        # Second response: end_turn
        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "No memories found."
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None

        cog.client.messages.create = AsyncMock(side_effect=[tool_response, final_response])

        messages = [{"role": "user", "content": "Check my memories"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        with patch("anthropic_api.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "No memory files found."

            parsed = await cog._call_api_with_tool_loop(
                api_params=api_params, messages=messages, user_id=123
            )

        assert parsed.text == "No memories found."
        assert cog.client.messages.create.call_count == 2
        # Messages should have: user, assistant (tool_use), user (tool_result), assistant (final)
        assert len(messages) == 4

    async def test_bash_tool_use_loop(self, cog):
        """bash tool_use triggers command execution and re-send."""
        # First response: bash tool_use
        tool_response = MagicMock()
        tool_text = MagicMock()
        tool_text.type = "text"
        tool_text.text = "Let me run that."
        tool_text.citations = None
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_456"
        tool_block.name = "bash"
        tool_block.input = {"command": "echo hello"}
        tool_response.content = [tool_text, tool_block]
        tool_response.stop_reason = "tool_use"
        tool_response.usage = None

        # Second response: end_turn
        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "The output was hello."
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = None

        cog.client.messages.create = AsyncMock(side_effect=[tool_response, final_response])

        messages = [{"role": "user", "content": "Run echo hello"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        with patch("anthropic_api.execute_bash_command", new_callable=AsyncMock) as mock_bash:
            mock_bash.return_value = "hello\n"

            parsed = await cog._call_api_with_tool_loop(
                api_params=api_params, messages=messages, user_id=123
            )

        assert parsed.text == "The output was hello."
        assert cog.client.messages.create.call_count == 2
        assert len(messages) == 4
        # Verify the tool result was sent back
        tool_result_msg = messages[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["content"] == "hello\n"

    async def test_max_iterations_safety(self, cog):
        """Loop stops at max_iterations."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Still working..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = None

        cog.client.messages.create = AsyncMock(return_value=pause_response)

        messages = [{"role": "user", "content": "Do something"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        await cog._call_api_with_tool_loop(
            api_params=api_params,
            messages=messages,
            user_id=123,
            max_iterations=3,
        )

        assert cog.client.messages.create.call_count == 3

    async def test_max_tokens_stop_reason(self, cog):
        """max_tokens stop reason is propagated on ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Truncated response..."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "max_tokens"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Write a long essay"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 10}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "max_tokens"
        assert parsed.text == "Truncated response..."
        assert len(messages) == 2

    async def test_refusal_stop_reason(self, cog):
        """refusal stop reason is propagated on ParsedResponse."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I can't help with that."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "refusal"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Bad request"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "refusal"

    async def test_context_window_exceeded_stop_reason(self, cog):
        """model_context_window_exceeded stop reason is propagated."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Partial response..."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "model_context_window_exceeded"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Very long conversation"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 64000}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.stop_reason == "model_context_window_exceeded"

    async def test_compaction_model_uses_beta_api(self, cog):
        """Compaction models use client.beta.messages.create with compaction params."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4-6", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "compact-2026-01-12" in call_kwargs["betas"]
        assert {"type": "compact_20260112"} in call_kwargs["context_management"]["edits"]
        assert call_kwargs["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    async def test_non_compaction_model_uses_regular_api(self, cog):
        """Non-compaction models without tools/thinking use client.messages.create."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.text == "Hello!"
        cog.client.messages.create.assert_called_once()
        call_kwargs = cog.client.messages.create.call_args[1]
        assert call_kwargs["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    async def test_context_editing_with_tools(self, cog):
        """Models with tools get context editing via beta API."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "tools": [{"type": "web_search_20260209", "name": "web_search"}],
        }

        await cog._call_api_with_tool_loop(api_params=api_params, messages=messages, user_id=123)

        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        assert "context-management-2025-06-27" in call_kwargs["betas"]
        edits = call_kwargs["context_management"]["edits"]
        tool_edits = [e for e in edits if e["type"] == "clear_tool_uses_20250919"]
        assert len(tool_edits) == 1

    async def test_context_editing_with_thinking(self, cog):
        """Models with thinking get thinking block clearing."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = None
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "thinking": {"type": "enabled", "budget_tokens": 5000},
        }

        await cog._call_api_with_tool_loop(api_params=api_params, messages=messages, user_id=123)

        cog.client.beta.messages.create.assert_called_once()
        call_kwargs = cog.client.beta.messages.create.call_args[1]
        edits = call_kwargs["context_management"]["edits"]
        thinking_edits = [e for e in edits if e["type"] == "clear_thinking_20251015"]
        assert len(thinking_edits) == 1
        # Thinking clearing must come before any other edits
        assert edits[0]["type"] == "clear_thinking_20251015"

    async def test_cache_tokens_accumulated(self, cog):
        """Cache creation and read tokens are accumulated across iterations."""
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = _make_usage(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=0,
        )

        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Done!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = _make_usage(
            input_tokens=50,
            output_tokens=30,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=200,
        )

        cog.client.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.input_tokens == 150
        assert parsed.output_tokens == 80
        assert parsed.cache_creation_tokens == 200
        assert parsed.cache_read_tokens == 200

    async def test_server_tool_use_accumulated(self, cog):
        """Server tool use counts are accumulated across iterations."""
        # First iteration: pause_turn with 2 web searches
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Searching..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        server_tool_use_1 = MagicMock(
            web_search_requests=2,
            web_fetch_requests=1,
            code_execution_requests=0,
        )
        pause_response.usage = MagicMock(
            input_tokens=100,
            output_tokens=50,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=server_tool_use_1,
        )

        # Second iteration: end_turn with 1 more web search
        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Found results!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        server_tool_use_2 = MagicMock(
            web_search_requests=1,
            web_fetch_requests=0,
            code_execution_requests=1,
        )
        final_response.usage = MagicMock(
            input_tokens=200,
            output_tokens=100,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            server_tool_use=server_tool_use_2,
        )

        cog.client.messages.create = AsyncMock(side_effect=[pause_response, final_response])

        messages = [{"role": "user", "content": "Search for something"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.web_search_requests == 3
        assert parsed.web_fetch_requests == 1
        assert parsed.code_execution_requests == 1

    async def test_server_tool_use_none_handled(self, cog):
        """Responses without server_tool_use don't break accumulation."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = _make_usage()

        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.web_search_requests == 0
        assert parsed.web_fetch_requests == 0
        assert parsed.code_execution_requests == 0

    async def test_context_warning_at_85_percent(self, cog):
        """context_warning is set when input tokens exceed 85% of context window."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        # 175k tokens is 87.5% of 200k — should trigger warning
        mock_response.usage = _make_usage(input_tokens=175_000, output_tokens=500)
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_warning is True
        assert parsed.context_compacted is False

    async def test_no_context_warning_below_threshold(self, cog):
        """context_warning is not set when input tokens are below 85%."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Response."
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        # 50k tokens is 25% of 200k — should NOT trigger warning
        mock_response.usage = _make_usage(input_tokens=50_000, output_tokens=500)
        cog.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_warning is False

    async def test_manual_compaction_triggers_at_75_percent(self, cog):
        """Non-compaction models trigger manual compaction when tokens exceed 75%."""
        # First response: pause_turn with 155k tokens (77.5% > 75% threshold)
        pause_response = MagicMock()
        pause_text = MagicMock()
        pause_text.type = "text"
        pause_text.text = "Working..."
        pause_text.citations = None
        pause_response.content = [pause_text]
        pause_response.stop_reason = "pause_turn"
        pause_response.usage = _make_usage(input_tokens=155_000, output_tokens=200)

        # Second response: end_turn (after compaction reduced context)
        final_response = MagicMock()
        final_text = MagicMock()
        final_text.type = "text"
        final_text.text = "Done!"
        final_text.citations = None
        final_response.content = [final_text]
        final_response.stop_reason = "end_turn"
        final_response.usage = _make_usage(input_tokens=2_000, output_tokens=100)

        # Summary response for _compact_conversation
        summary_response = MagicMock()
        summary_text = MagicMock()
        summary_text.type = "text"
        summary_text.text = "<summary>Conversation summary here.</summary>"
        summary_response.content = [summary_text]

        cog.client.messages.create = AsyncMock(
            side_effect=[pause_response, summary_response, final_response]
        )

        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Continue"},
        ]
        api_params = {"model": "claude-haiku-4-5", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_compacted is True
        assert parsed.text == "Done!"
        # 3 API calls: original, compaction summary, post-compaction
        assert cog.client.messages.create.call_count == 3

    async def test_compaction_model_skips_manual_compaction(self, cog):
        """Compaction models (server-side) never trigger manual compaction."""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        text_block.citations = None
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        # High token count, but server-side compaction handles it
        mock_response.usage = _make_usage(input_tokens=180_000, output_tokens=500)
        cog.client.beta.messages.create = AsyncMock(return_value=mock_response)

        messages = [{"role": "user", "content": "Hi"}]
        api_params = {"model": "claude-sonnet-4-6", "max_tokens": 1024}

        parsed = await cog._call_api_with_tool_loop(
            api_params=api_params, messages=messages, user_id=123
        )

        assert parsed.context_compacted is False
        # Warning still fires since 180k > 85% of 200k
        assert parsed.context_warning is True
        # Only 1 API call (no compaction call)
        cog.client.beta.messages.create.assert_called_once()


class TestContextEmbeds:
    """Tests for context warning and compaction embed helpers."""

    def test_context_warning_embed(self):
        from anthropic_api import append_context_warning_embed

        embeds = []
        append_context_warning_embed(embeds)
        assert len(embeds) == 1
        assert embeds[0].title == "Context Window Warning"
        assert "85%" in embeds[0].description

    def test_compaction_embed(self):
        from anthropic_api import append_compaction_embed

        embeds = []
        append_compaction_embed(embeds)
        assert len(embeds) == 1
        assert embeds[0].title == "Context Compacted"
        assert "summarized" in embeds[0].description


class TestToolHandlerRegistry:
    """Tests for the tool handler registry pattern."""

    @pytest.fixture
    def cog(self, mock_bot):
        with patch("anthropic.AsyncAnthropic"):
            from anthropic_api import AnthropicAPI

            return AnthropicAPI(bot=mock_bot)

    async def test_memory_tool_dispatches(self, cog):
        """Memory tool is dispatched via the registry."""
        with patch("anthropic_api.execute_memory_operation") as mock_exec:
            mock_exec.return_value = "Memory result."
            result = await cog._execute_tool(
                "memory", {"command": "view", "path": "/memories"}, user_id=123
            )
        assert result == "Memory result."
        mock_exec.assert_called_once_with(
            user_id=123,
            tool_input={"command": "view", "path": "/memories"},
        )

    async def test_bash_tool_dispatches(self, cog):
        """Bash tool is dispatched via the registry."""
        with patch("anthropic_api.execute_bash_command", new_callable=AsyncMock) as mock_bash:
            mock_bash.return_value = "hello\n"
            result = await cog._execute_tool("bash", {"command": "echo hello"}, user_id=123)
        assert result == "hello\n"

    async def test_bash_restart_handled(self, cog):
        """Bash restart command returns restart message."""
        result = await cog._execute_tool("bash", {"restart": True}, user_id=123)
        assert result == "Bash session restarted."

    async def test_unknown_tool_returns_error(self, cog):
        """Unknown tool names return an error string."""
        result = await cog._execute_tool("nonexistent", {}, user_id=123)
        assert "Error: Unknown tool" in result
