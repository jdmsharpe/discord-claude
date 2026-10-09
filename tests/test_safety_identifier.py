"""The keyed identifier reaches every Messages request made for a Discord user."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

USER_ID = 987654321098765432
KEY = b"test-safety-identifier-secret"
EXPECTED_IDENTIFIER = hmac.new(KEY, str(USER_ID).encode(), hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _fixed_key(monkeypatch):
    monkeypatch.setattr("discord_claude.util.SAFETY_IDENTIFIER_KEY", KEY)


@pytest.fixture
def cog(mock_bot):
    with patch("discord_claude.cogs.claude.client.AsyncAnthropic") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client

        from discord_claude.cogs.claude.cog import ClaudeCog

        cog = ClaudeCog(bot=mock_bot)
        cog.client = mock_client
        return cog


def _usage(input_tokens=10, output_tokens=15):
    return MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        server_tool_use=None,
        iterations=None,
    )


def _text_response(text="Answer.", stop_reason="end_turn", usage=None):
    block = MagicMock()
    block.type = "text"
    block.text = text
    block.citations = None
    response = MagicMock()
    response.content = [block]
    response.stop_reason = stop_reason
    response.stop_details = None
    response.usage = usage or _usage()
    return response


def _tool_use_response():
    block = MagicMock()
    block.type = "tool_use"
    block.id = "toolu_01"
    block.name = "memory"
    block.input = {"command": "view", "path": "/memories"}
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "tool_use"
    response.stop_details = None
    response.usage = _usage()
    return response


def _summary_response(usage):
    block = MagicMock()
    block.type = "text"
    block.text = '{"task": "t", "key_context": "k", "current_state": "c", "next_steps": "n"}'
    response = MagicMock()
    response.content = [block]
    response.stop_reason = "end_turn"
    response.usage = usage
    return response


def _assert_carries_identifier_only(kwargs: dict) -> None:
    assert kwargs["metadata"] == {"user_id": EXPECTED_IDENTIFIER}
    serialized = json.dumps(kwargs, default=repr)
    assert str(USER_ID) not in serialized
    assert format(USER_ID, "x") not in serialized


def _route(chat_responses, summary):
    """A messages.create side effect: the summarizer call (output_config.format set)
    gets ``summary``; every other call takes the next of ``chat_responses``."""
    remaining = iter(chat_responses)

    async def create(**kwargs):
        if "format" in (kwargs.get("output_config") or {}):
            return summary
        return next(remaining)

    return create


async def test_every_tool_loop_request_sends_the_identifier(cog):
    """Both iterations of a tool loop on the beta surface carry metadata.user_id."""
    cog.client.beta.messages.create = AsyncMock(
        side_effect=[_tool_use_response(), _text_response()]
    )
    cog._execute_tool = AsyncMock(return_value="no memories")

    await cog._call_api_with_tool_loop(
        api_params={"model": "claude-opus-5-5", "max_tokens": 1024},
        messages=[{"role": "user", "content": "Hi"}],
        user_id=USER_ID,
    )

    calls = cog.client.beta.messages.create.await_args_list
    assert len(calls) == 2
    for call in calls:
        _assert_carries_identifier_only(call.kwargs)


async def test_non_beta_request_sends_the_identifier(cog):
    cog.client.messages.create = AsyncMock(return_value=_text_response())

    await cog._call_api_with_tool_loop(
        api_params={"model": "claude-haiku-4-5", "max_tokens": 1024},
        messages=[{"role": "user", "content": "Hi"}],
        user_id=USER_ID,
    )

    _assert_carries_identifier_only(cog.client.messages.create.await_args.kwargs)


async def test_manual_compaction_summarizer_sends_the_identifier(cog):
    cog.client.messages.create = AsyncMock(
        side_effect=_route(
            [_text_response(usage=_usage(input_tokens=160_000))],
            _summary_response(_usage(input_tokens=160_100, output_tokens=300)),
        )
    )

    parsed = await cog._call_api_with_tool_loop(
        api_params={"model": "claude-haiku-4-5", "max_tokens": 1024},
        messages=[
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ],
        user_id=USER_ID,
    )

    assert parsed.context_compacted is True
    calls = cog.client.messages.create.await_args_list
    assert len(calls) == 2
    assert "format" in calls[1].kwargs["output_config"]
    for call in calls:
        _assert_carries_identifier_only(call.kwargs)


async def test_compact_conversation_without_a_user_sends_no_metadata():
    from discord_claude.cogs.claude.state import compact_conversation

    cog = MagicMock()
    cog.client.messages.create = AsyncMock(return_value=_summary_response(_usage()))

    await compact_conversation(cog, [{"role": "user", "content": "x"}])

    assert "metadata" not in cog.client.messages.create.await_args.kwargs


async def test_requests_send_no_metadata_without_a_key(cog, monkeypatch):
    monkeypatch.setattr("discord_claude.util.SAFETY_IDENTIFIER_KEY", None)
    cog.client.messages.create = AsyncMock(
        side_effect=_route(
            [_text_response(usage=_usage(input_tokens=160_000))],
            _summary_response(_usage(input_tokens=160_100, output_tokens=300)),
        )
    )

    await cog._call_api_with_tool_loop(
        api_params={"model": "claude-haiku-4-5", "max_tokens": 1024},
        messages=[
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Second question"},
        ],
        user_id=USER_ID,
    )

    calls = cog.client.messages.create.await_args_list
    assert len(calls) == 2
    for call in calls:
        assert "metadata" not in call.kwargs
        assert str(USER_ID) not in json.dumps(call.kwargs, default=repr)


async def test_chat_command_request_sends_the_identifier(cog, mock_discord_context):
    mock_discord_context.author.id = USER_ID
    mock_discord_context.send_followup = AsyncMock(return_value=MagicMock(id=123))
    cog.client.beta.messages.create = AsyncMock(return_value=_text_response())

    with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
        await cog.chat.callback(cog, ctx=mock_discord_context, prompt="Hello")

    cog.client.beta.messages.create.assert_awaited_once()
    _assert_carries_identifier_only(cog.client.beta.messages.create.await_args.kwargs)


async def test_follow_up_message_request_sends_the_identifier(cog, mock_discord_message):
    from discord_claude.util import ChatCompletionParameters, Conversation

    mock_discord_message.author.id = USER_ID
    mock_discord_message.reply = AsyncMock(return_value=MagicMock(id=456))
    cog.client.beta.messages.create = AsyncMock(return_value=_text_response())
    params = ChatCompletionParameters(
        model="claude-opus-5-5",
        conversation_starter=mock_discord_message.author,
        channel_id=mock_discord_message.channel.id,
        conversation_id=123,
    )
    conversation = Conversation(
        params=params,
        messages=[
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ],
    )
    cog.conversations[(USER_ID, mock_discord_message.channel.id)] = conversation

    with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
        await cog.handle_new_message_in_conversation(mock_discord_message, conversation)

    cog.client.beta.messages.create.assert_awaited_once()
    _assert_carries_identifier_only(cog.client.beta.messages.create.await_args.kwargs)
