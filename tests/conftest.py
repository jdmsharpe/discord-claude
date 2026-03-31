from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot instance."""
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.owner_id = 987654321
    bot.sync_commands = AsyncMock()
    return bot


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    with patch("discord_claude.cogs.claude.client.AsyncAnthropic") as mock_class:
        client = AsyncMock()
        mock_class.return_value = client

        # Mock messages.create response
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello! How can I help you today?"
        mock_response.content = [text_block]
        mock_response.id = "msg_01XFDUDYJgAACzvnptvVoYEL"
        mock_response.model = "claude-sonnet-4"
        mock_response.stop_reason = "end_turn"
        mock_response.usage = make_mock_usage()

        client.messages.create = AsyncMock(return_value=mock_response)

        yield client


@pytest.fixture
def mock_discord_context():
    """Create a mock Discord application context."""
    ctx = AsyncMock()
    ctx.author = MagicMock()
    ctx.author.id = 111222333
    ctx.author.name = "TestUser"
    ctx.channel = MagicMock()
    ctx.channel.id = 444555666
    ctx.interaction = MagicMock()
    ctx.interaction.id = 777888999
    ctx.defer = AsyncMock()
    ctx.send_followup = AsyncMock()
    ctx.respond = AsyncMock()
    return ctx


@pytest.fixture
def mock_discord_message():
    """Create a mock Discord message."""
    message = MagicMock()
    message.author = MagicMock()
    message.author.id = 111222333
    message.author.name = "TestUser"
    message.channel = MagicMock()
    message.channel.id = 444555666
    message.content = "Hello Claude!"
    message.attachments = []
    message.reply = AsyncMock()
    return message


@pytest.fixture
def mock_attachment():
    """Create a mock Discord attachment."""
    attachment = MagicMock()
    attachment.url = "https://example.com/image.png"
    attachment.content_type = "image/png"
    attachment.filename = "image.png"
    return attachment


@pytest.fixture
def sample_messages():
    """Sample conversation messages."""
    return [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you?"},
        {"role": "user", "content": "What is Python?"},
    ]


@pytest.fixture
def sample_api_response():
    """Sample Anthropic API response structure."""
    return {
        "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello! How can I help you today?"}],
        "model": "claude-sonnet-4",
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 15},
    }


def make_mock_usage(
    input_tokens=10,
    output_tokens=15,
    cache_creation_input_tokens=0,
    cache_read_input_tokens=0,
    web_search_requests=0,
    web_fetch_requests=0,
    code_execution_requests=0,
):
    """Create a mock usage object with proper numeric values and server_tool_use."""
    server_tool_use = None
    if web_search_requests or web_fetch_requests or code_execution_requests:
        server_tool_use = MagicMock(
            web_search_requests=web_search_requests,
            web_fetch_requests=web_fetch_requests,
            code_execution_requests=code_execution_requests,
        )
    return MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=cache_creation_input_tokens,
        cache_read_input_tokens=cache_read_input_tokens,
        server_tool_use=server_tool_use,
    )


@pytest.fixture
def mock_tool_use_response():
    """Mock response with a client-side tool_use block (memory)."""
    response = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Let me check your memories."
    text_block.citations = None
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = "toolu_01abc123"
    tool_block.name = "memory"
    tool_block.input = {"command": "view", "path": "/memories"}
    response.content = [text_block, tool_block]
    response.stop_reason = "tool_use"
    response.usage = make_mock_usage()
    return response


@pytest.fixture
def mock_web_search_response():
    """Mock response with server-side web search results and citations."""
    response = MagicMock()

    server_block = MagicMock()
    server_block.type = "server_tool_use"
    server_block.id = "srvtoolu_01xyz"
    server_block.name = "web_search"

    result_block = MagicMock()
    result_block.type = "web_search_tool_result"

    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "According to recent sources..."
    citation = MagicMock()
    citation.url = "https://example.com/article"
    citation.title = "Example Article"
    citation.cited_text = "some cited text"
    text_block.citations = [citation]

    response.content = [server_block, result_block, text_block]
    response.stop_reason = "end_turn"
    response.usage = make_mock_usage(web_search_requests=1)
    return response
