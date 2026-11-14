"""Changing a conversation's tools while its history holds thinking blocks.

Models with preserved thinking (Fable 5.2 on every account) return 400 when a thinking
block comes back after the `tools` array sent before it has changed. `FakeMessagesApi`
applies that rule to requests made through the real SDK client, so these tests fail if
the bot replays thinking blocks under a different tool list.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import AsyncAnthropic

from discord_claude.cogs.claude.chat import (
    drop_thinking_on_tool_change,
    strip_thinking_blocks,
    tools_fingerprint,
)
from discord_claude.cogs.claude.tool_registry import TOOL_REGISTRY, get_anthropic_tools
from discord_claude.util import ChatCompletionParameters, Conversation

MODEL = "claude-fable-5-2"
MISMATCH_MESSAGE = (
    "messages.1.content.0: Invalid `signature` in `thinking` block. The block is bound "
    "to a different conversation. Remove the block, or set "
    '`thinking.block_binding.prefix_mismatch_behavior` to "drop_block". '
    "The tools list differs from the one this block was created with."
)


def _replayed_thinking(body):
    return [
        block
        for message in body["messages"]
        if message["role"] == "assistant" and isinstance(message["content"], list)
        for block in message["content"]
        if block["type"] in {"thinking", "redacted_thinking"}
    ]


class FakeMessagesApi:
    """Answers Messages requests and rejects thinking replayed under a changed tool list."""

    def __init__(self):
        self.bodies = []
        self.statuses = []
        self.tools_of_last_answer = None
        # Set to make the next request look as if the tools changed on the server side,
        # which the bot cannot see in its own request (an MCP server's tool list).
        self.invalidate_thinking_once = False

    def __call__(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        tools = sorted(json.dumps(tool, sort_keys=True) for tool in body.get("tools", []))
        replayed = _replayed_thinking(body)
        changed = tools != self.tools_of_last_answer or self.invalidate_thinking_once
        if replayed and changed:
            self.invalidate_thinking_once = False
            self.statuses.append(400)
            return httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": MISMATCH_MESSAGE},
                },
            )
        self.tools_of_last_answer = tools
        self.statuses.append(200)
        turn = self.statuses.count(200)
        return httpx2.Response(
            200,
            json={
                "id": f"msg_{turn}",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [
                    {"type": "thinking", "thinking": "", "signature": f"signature-{turn}"},
                    {"type": "text", "text": f"Answer {turn}."},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )


@pytest.fixture
def api():
    return FakeMessagesApi()


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


async def _start_conversation(cog, ctx, **options) -> Conversation:
    ctx.send_followup = AsyncMock(return_value=MagicMock(id=123))
    with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
        await cog.chat.callback(cog, ctx=ctx, prompt="First question", model=MODEL, **options)
    return cog.conversations[(ctx.author.id, ctx.channel.id)]


async def _select_tools(cog, ctx, values) -> None:
    """Choose tools in the conversation's Tools dropdown, as the user does in Discord."""
    interaction = MagicMock()
    interaction.user = ctx.author
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=False)
    await cog.views[ctx.author].tool_select_callback(interaction, SimpleNamespace(values=values))


async def _follow_up(cog, ctx, message):
    """Send a follow-up message and return the titles of the embeds in the reply."""
    message.author = ctx.author
    message.stickers = []
    message.reply = AsyncMock(return_value=MagicMock(id=456))
    with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
        await cog.handle_new_message_in_conversation(
            message, cog.conversations[(ctx.author.id, ctx.channel.id)]
        )
    titles = []
    for call in message.reply.await_args_list:
        embeds = call.kwargs.get("embeds") or [call.kwargs.get("embed")]
        titles.extend(embed.title for embed in embeds if embed is not None)
    return titles


class TestToolChangeBetweenTurns:
    async def test_enabling_a_tool_sends_the_next_request_without_earlier_thinking(
        self, cog, api, mock_discord_context, mock_discord_message
    ):
        """The reported failure: a chat started without tools, then Web Search enabled in
        the dropdown, then a follow-up. The follow-up used to replay the first reply's
        thinking block under the new tool list, got a 400 and ended the conversation."""
        conversation = await _start_conversation(cog, mock_discord_context)
        assert [block.type for block in conversation.messages[1]["content"]] == ["thinking", "text"]
        assert "tools" not in api.bodies[0]

        await _select_tools(cog, mock_discord_context, ["web_search"])
        titles = await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert api.statuses == [200, 200]
        assert "Error" not in titles
        assert [tool["name"] for tool in api.bodies[1]["tools"]] == ["web_search"]
        assert _replayed_thinking(api.bodies[1]) == []
        assert api.bodies[1]["messages"][1]["content"] == [{"type": "text", "text": "Answer 1."}]
        key = (mock_discord_context.author.id, mock_discord_context.channel.id)
        assert cog.conversations[key] is conversation

    @pytest.mark.parametrize(
        ("started_with", "selected"),
        [
            ({"web_search": True}, []),
            ({"web_search": True}, ["code_execution"]),
            ({"web_search": True}, ["web_search", "code_execution"]),
        ],
    )
    async def test_removing_or_swapping_a_tool_also_drops_earlier_thinking(
        self, cog, api, mock_discord_context, mock_discord_message, started_with, selected
    ):
        await _start_conversation(cog, mock_discord_context, **started_with)

        await _select_tools(cog, mock_discord_context, selected)
        titles = await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert api.statuses == [200, 200]
        assert "Error" not in titles
        assert [tool["name"] for tool in api.bodies[1].get("tools", [])] == selected
        assert _replayed_thinking(api.bodies[1]) == []

    async def test_thinking_from_after_the_change_is_replayed(
        self, cog, api, mock_discord_context, mock_discord_message
    ):
        """Only the thinking produced under the old tools is removed. The reply to the
        first request with the new tools keeps its thinking block on later turns."""
        await _start_conversation(cog, mock_discord_context)
        await _select_tools(cog, mock_discord_context, ["web_search"])
        await _follow_up(cog, mock_discord_context, mock_discord_message)

        titles = await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert api.statuses == [200, 200, 200]
        assert "Error" not in titles
        assert [block["signature"] for block in _replayed_thinking(api.bodies[2])] == [
            "signature-2"
        ]

    async def test_unchanged_tools_replay_every_thinking_block(
        self, cog, api, mock_discord_context, mock_discord_message
    ):
        """Without a tool change the history stays as the API returned it, so the model
        keeps its earlier reasoning and the prompt cache keeps matching."""
        await _start_conversation(cog, mock_discord_context, web_search=True)

        await _follow_up(cog, mock_discord_context, mock_discord_message)
        await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert api.statuses == [200, 200, 200]
        assert [block["signature"] for block in _replayed_thinking(api.bodies[2])] == [
            "signature-1",
            "signature-2",
        ]

    async def test_selecting_the_same_tools_again_keeps_the_thinking(
        self, cog, api, mock_discord_context, mock_discord_message
    ):
        await _start_conversation(cog, mock_discord_context, web_search=True)

        await _select_tools(cog, mock_discord_context, ["web_search", "memory"])
        await _select_tools(cog, mock_discord_context, ["web_search"])
        await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert api.statuses == [200, 200]
        assert [block["signature"] for block in _replayed_thinking(api.bodies[1])] == [
            "signature-1"
        ]


class TestPrefixMismatchRecovery:
    async def test_a_mismatch_the_bot_did_not_cause_is_retried_without_thinking(
        self, cog, api, mock_discord_context, mock_discord_message, caplog
    ):
        await _start_conversation(cog, mock_discord_context, web_search=True)
        api.invalidate_thinking_once = True

        with caplog.at_level(logging.WARNING):
            titles = await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert api.statuses == [200, 400, 200]
        assert "Error" not in titles
        assert _replayed_thinking(api.bodies[1]) != []
        assert _replayed_thinking(api.bodies[2]) == []
        assert "removed them and sent the request again" in caplog.text
        key = (mock_discord_context.author.id, mock_discord_context.channel.id)
        assert key in cog.conversations

    async def test_another_400_is_not_retried(
        self, cog, mock_discord_context, mock_discord_message
    ):
        await _start_conversation(cog, mock_discord_context)
        requests = []

        def reject(request):
            requests.append(request)
            return httpx2.Response(
                400,
                json={
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": "max_tokens: too large"},
                },
            )

        async with AsyncAnthropic(
            api_key="test-only",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(reject)),
        ) as client:
            cog.client = client
            titles = await _follow_up(cog, mock_discord_context, mock_discord_message)

        assert len(requests) == 1
        assert "Error" in titles


class TestStripThinkingBlocks:
    def test_removes_dict_and_typed_blocks_and_counts_them(self):
        text = SimpleNamespace(type="text", text="typed answer")
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "question"}]},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "", "signature": "a"},
                    {"type": "redacted_thinking", "data": "b"},
                    {"type": "text", "text": "answer"},
                ],
            },
            {"role": "user", "content": "plain string"},
            {
                "role": "assistant",
                "content": [SimpleNamespace(type="thinking", thinking="", signature="c"), text],
            },
        ]
        history = messages

        assert strip_thinking_blocks(messages) == 3

        assert messages is history
        assert messages[1]["content"] == [{"type": "text", "text": "answer"}]
        assert messages[3]["content"] == [text]
        assert messages[0]["content"] == [{"type": "text", "text": "question"}]

    def test_removes_an_assistant_message_that_held_only_thinking(self):
        messages = [
            {"role": "user", "content": "one"},
            {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "", "signature": "a"}],
            },
            {"role": "user", "content": "two"},
        ]

        assert strip_thinking_blocks(messages) == 1

        assert messages == [{"role": "user", "content": "one"}, {"role": "user", "content": "two"}]

    def test_leaves_a_history_without_thinking_untouched(self):
        messages = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "string content"},
            {"role": "system", "content": [], "output_config": {"effort": "low"}},
            {
                "role": "user",
                "content": [{"type": "thinking", "thinking": "not an assistant turn"}],
            },
        ]
        before = json.loads(json.dumps(messages))

        assert strip_thinking_blocks(messages) == 0

        assert messages == before


class TestToolsFingerprint:
    def test_ignores_order_and_detects_any_definition_change(self):
        tools = get_anthropic_tools(["web_search", "code_execution"])

        assert tools_fingerprint(tools) == tools_fingerprint(list(reversed(tools)))
        assert tools_fingerprint(None) == tools_fingerprint([]) == []
        assert tools_fingerprint(tools) != tools_fingerprint(tools[:1])
        assert tools_fingerprint([{**tools[0], "max_uses": 6}]) != tools_fingerprint(tools[:1])

    @pytest.mark.parametrize("tool_id", sorted(TOOL_REGISTRY))
    def test_every_registry_tool_can_be_fingerprinted(self, tool_id):
        assert tools_fingerprint(get_anthropic_tools([tool_id]))

    def test_a_conversation_without_a_recorded_tool_list_only_records_it(self):
        thinking = {"type": "thinking", "thinking": "", "signature": "a"}
        conversation = Conversation(
            params=ChatCompletionParameters(model=MODEL),
            messages=[{"role": "assistant", "content": [thinking, {"type": "text", "text": "x"}]}],
        )
        tools = get_anthropic_tools(["web_search"])

        drop_thinking_on_tool_change(MagicMock(), conversation, {"tools": tools})

        assert conversation.request_tools == tools_fingerprint(tools)
        assert conversation.messages[0]["content"][0] == thinking
