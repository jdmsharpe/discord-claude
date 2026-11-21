"""MCP tool listings recorded by the API (`mcp_tool_listing` blocks, beta `mcp-client-2026-09-15`).

The bot runs the chat command and a follow-up through the real SDK client against a fake
API. It checks the request header, that the listing block comes back in the next request
exactly as the API returned it, and that nothing of it is shown in Discord.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import AsyncAnthropic

from discord_claude.cogs.claude.chat import strip_thinking_blocks
from discord_claude.cogs.claude.responses import extract_response_content
from discord_claude.config.mcp import AnthropicMcpPreset

MODEL = "claude-opus-5-5"
NEW_BETA = "mcp-client-2026-09-15"
OLD_BETA = "mcp-client-2025-11-20"
LISTING = {
    "type": "mcp_tool_listing",
    "mcp_server_name": "files",
    "tools": [
        {
            "name": "echo",
            "description": "Returns the text it receives.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
        {"name": "ping", "input_schema": {"type": "object"}},
    ],
}


class FakeMcpApi:
    """Answers the first request with a tool listing, as the API does when it asks the server."""

    def __init__(self):
        self.bodies = []
        self.betas = []

    def __call__(self, request):
        self.bodies.append(json.loads(request.content))
        self.betas.append(request.headers.get("anthropic-beta", "").split(","))
        turn = len(self.bodies)
        content = [{"type": "text", "text": f"Answer {turn}."}]
        if turn == 1:
            content.insert(0, LISTING)
        return httpx2.Response(
            200,
            json={
                "id": f"msg_{turn}",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": content,
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )


@pytest.fixture
def api():
    return FakeMcpApi()


@pytest.fixture
async def cog(mock_bot, api):
    from discord_claude.cogs.claude.cog import ClaudeCog

    cog = ClaudeCog(bot=mock_bot)
    async with AsyncAnthropic(
        api_key="test-only",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(api)),
    ) as client:
        cog.client = client
        yield cog


@pytest.fixture(autouse=True)
def files_preset():
    preset = AnthropicMcpPreset(name="files", server_url="https://mcp.example.com/sse")
    with patch.dict("discord_claude.config.mcp.ANTHROPIC_MCP_PRESETS", {"files": preset}):
        yield


def _embeds(mock) -> list:
    embeds = []
    for call in mock.await_args_list:
        embeds.extend(call.kwargs.get("embeds") or [call.kwargs.get("embed")])
    return [embed for embed in embeds if embed is not None]


def _shown_text(embeds) -> str:
    return "\n".join(f"{embed.title}\n{embed.description}" for embed in embeds)


class TestMcpToolListingRoundTrip:
    async def test_the_listing_is_sent_back_unchanged_and_never_shown(
        self, cog, api, mock_discord_context, mock_discord_message
    ):
        ctx = mock_discord_context
        ctx.send_followup = AsyncMock(return_value=MagicMock(id=123))
        with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
            await cog.chat.callback(cog, ctx=ctx, prompt="List files", model=MODEL, mcp="files")
        conversation = cog.conversations[(ctx.author.id, ctx.channel.id)]
        message = mock_discord_message
        message.author = ctx.author
        message.stickers = []
        message.reply = AsyncMock(return_value=MagicMock(id=456))
        with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
            await cog.handle_new_message_in_conversation(message, conversation)

        # Both requests carry the new header and not the older one.
        assert len(api.bodies) == 2
        for betas in api.betas:
            assert NEW_BETA in betas
            assert OLD_BETA not in betas
        for body in api.bodies:
            assert body["mcp_servers"] == [
                {"type": "url", "url": "https://mcp.example.com/sse", "name": "files"}
            ]
            assert {"type": "mcp_toolset", "mcp_server_name": "files"} in body["tools"]

        # The stored history holds the listing, and the second request replays it as the
        # API returned it (field for field, in front of the text block).
        assert [block.type for block in conversation.messages[1]["content"]] == [
            "mcp_tool_listing",
            "text",
        ]
        assert api.bodies[1]["messages"][1] == {
            "role": "assistant",
            "content": [LISTING, {"type": "text", "text": "Answer 1."}],
        }

        # Neither reply shows the listing or its tools.
        shown = _shown_text(_embeds(ctx.send_followup) + _embeds(message.reply))
        assert "Answer 1." in shown
        assert "Answer 2." in shown
        for hidden in ("mcp_tool_listing", "echo", "ping", "Returns the text it receives."):
            assert hidden not in shown
        assert "Error" not in {embed.title for embed in _embeds(message.reply)}

    def test_a_response_with_a_listing_renders_only_its_text(self):
        response = SimpleNamespace(
            content=[
                SimpleNamespace(type="mcp_tool_listing", mcp_server_name="files", tools=[]),
                SimpleNamespace(type="text", text="Answer.", citations=None),
            ]
        )

        parsed = extract_response_content(response)

        assert parsed.text == "Answer."
        assert parsed.tool_use_blocks == []

    def test_dropping_thinking_after_a_prefix_mismatch_keeps_the_listing(self):
        thinking = {"type": "thinking", "thinking": "", "signature": "a"}
        text = {"type": "text", "text": "Answer."}
        messages = [{"role": "assistant", "content": [LISTING, thinking, text]}]

        assert strip_thinking_blocks(messages) == 1

        assert messages[0]["content"] == [LISTING, text]
