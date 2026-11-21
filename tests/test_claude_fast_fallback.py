"""A fast-mode request that gets a 429 or 529 is sent once more at standard speed.

Requests go through the real SDK client to a fake API that answers each request from a
script, keyed by whether its body sets `speed: "fast"`, so every test checks the request
bodies the bot really sends, how many the SDK sends, and the cost it bills. Error
responses carry `retry-after-ms: 1`, so a test client with SDK retries waits one
millisecond between them.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from anthropic import AsyncAnthropic

from discord_claude.cogs.claude.chat import build_api_params, call_api_with_tool_loop
from discord_claude.util import ChatCompletionParameters, calculate_cost

MODEL = "claude-opus-5-5"
FALLBACK_TARGET = "claude-opus-4-8"
COUNTS = {
    "input_tokens": 1000,
    "output_tokens": 100,
    "cache_creation_input_tokens": 200,
    "cache_read_input_tokens": 300,
}
STANDARD_COST = calculate_cost(MODEL, 1000, 100, 200, 300)
FALLBACK_COST = calculate_cost(FALLBACK_TARGET, 1000, 100, 200, 300)
NOTICE_TITLE = "Fast Mode Unavailable"

# A script entry is None (answer 200), (status, error body) or (status, error body, headers),
# or CONNECTION_ERROR (the connection fails).
CONNECTION_ERROR = "connection error"
CAPACITY_ERRORS = {
    429: (429, {"type": "rate_limit_error", "message": "Fast mode rate limit exceeded."}),
    529: (529, {"type": "overloaded_error", "message": "Fast mode is overloaded."}),
}


def _error(status, message, code=None, error_type=None):
    """An API error with a specific `error_code`, as spend limits and similar errors carry."""
    kind = error_type or ("overloaded_error" if status == 529 else "rate_limit_error")
    body = {"type": kind, "message": message}
    if code is not None:
        body["details"] = {"error_code": code}
    return (status, body)


def _usage(speed, counts=COUNTS):
    return {**counts, "speed": speed}


class FakeApi:
    """Answers requests from `fast_script` (bodies with `speed: "fast"`) and `standard_script`.

    Each script is consumed one entry per request of its kind, and its last entry repeats.
    """

    def __init__(self, fast_script=(None,), standard_script=(None,), standard_usage=None):
        self.scripts = {True: list(fast_script), False: list(standard_script)}
        self.seen = {True: 0, False: 0}
        self.standard_usage = standard_usage
        self.bodies = []
        self.statuses = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        fast = body.get("speed") == "fast"
        script = self.scripts[fast]
        entry = script[min(self.seen[fast], len(script) - 1)]
        self.seen[fast] += 1
        if entry == CONNECTION_ERROR:
            self.statuses.append(CONNECTION_ERROR)
            raise httpx2.ConnectError("connection failed", request=request)
        if entry is not None:
            status, error, *headers = entry
            self.statuses.append(status)
            return httpx2.Response(
                status,
                json={"type": "error", "error": error},
                headers={"retry-after-ms": "1", **(headers[0] if headers else {})},
            )
        self.statuses.append(200)
        usage = _usage("fast" if fast else "standard")
        if not fast and self.standard_usage:
            usage = self.standard_usage
        return httpx2.Response(
            200,
            json={
                "id": f"msg_{len(self.bodies)}",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [{"type": "text", "text": "Answer."}],
                "stop_reason": "end_turn",
                "usage": usage,
            },
        )


class ToolLoopApi:
    """Two tool turns: request 1 runs fast; every later fast request gets a 429.

    Requests 1 and 3 (or the first two successful ones) ask for a tool; the next one answers.
    """

    def __init__(self):
        self.bodies = []
        self.statuses = []
        self.answered = 0

    def __call__(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        fast = body.get("speed") == "fast"
        if fast and len(self.bodies) > 1:
            self.statuses.append(429)
            return httpx2.Response(
                429,
                json={"type": "error", "error": CAPACITY_ERRORS[429][1]},
                headers={"retry-after-ms": "1"},
            )
        self.statuses.append(200)
        self.answered += 1
        asks_for_tool = self.answered <= 2
        return httpx2.Response(
            200,
            json={
                "id": f"msg_{len(self.bodies)}",
                "type": "message",
                "role": "assistant",
                "model": MODEL,
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"toolu_{self.answered}",
                        "name": "memory",
                        "input": {"command": "view", "path": "/memories"},
                    }
                ]
                if asks_for_tool
                else [{"type": "text", "text": "Done."}],
                "stop_reason": "tool_use" if asks_for_tool else "end_turn",
                "usage": _usage("fast" if fast else "standard"),
            },
        )


@pytest.fixture
async def make_cog(mock_bot):
    """Build a cog whose real SDK client talks to `api`, a function of the request."""
    from discord_claude.cogs.claude.cog import ClaudeCog

    clients = []

    def make(api, max_retries=0):
        cog = ClaudeCog(bot=mock_bot)
        cog.client = AsyncAnthropic(
            api_key="test-only",
            max_retries=max_retries,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(api)),
        )
        clients.append(cog.client)
        return cog

    yield make
    for client in clients:
        await client.close()


def _record_costs(cog):
    """Return the list that collects the request cost the cog bills for each reply."""
    costs = []
    track_daily_cost = cog._track_daily_cost

    def record_cost(*args, **kwargs):
        result = track_daily_cost(*args, **kwargs)
        costs.append(result[0])
        return result

    cog._track_daily_cost = record_cost
    return costs


def _embeds_sent(mock):
    embeds = []
    for call in mock.await_args_list:
        embeds.extend(call.kwargs.get("embeds") or [call.kwargs.get("embed")])
    return [embed for embed in embeds if embed is not None]


async def _chat(cog, ctx, **options):
    """Run `/claude chat` and return (embeds shown, request costs billed)."""
    costs = _record_costs(cog)
    ctx.send_followup = AsyncMock(return_value=MagicMock(id=123))
    with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
        await cog.chat.callback(cog, ctx=ctx, prompt="Question", model=MODEL, **options)
    return _embeds_sent(ctx.send_followup), costs


def _titles(embeds):
    return [embed.title for embed in embeds]


class TestFastCapacityFallback:
    @pytest.mark.parametrize("status", [429, 529])
    async def test_the_request_is_sent_once_more_without_speed(
        self, make_cog, mock_discord_context, status
    ):
        api = FakeApi(fast_script=[CAPACITY_ERRORS[status]])
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [status, 200]
        first, second = api.bodies
        assert first["speed"] == "fast"
        # Refusal fallbacks are asked to run at standard speed while the request is fast.
        assert first["fallbacks"] == [{"model": FALLBACK_TARGET, "speed": "standard"}]
        assert "speed" not in second
        # The request is otherwise the one a standard-speed conversation sends.
        assert second == {
            **{key: value for key, value in first.items() if key != "speed"},
            "fallbacks": [{"model": FALLBACK_TARGET}],
        }
        assert _titles(embeds).count(NOTICE_TITLE) == 1
        notice = next(embed for embed in embeds if embed.title == NOTICE_TITLE)
        assert notice.description == (
            "Fast mode was at capacity, so this reply ran at standard speed."
        )
        assert "Error" not in _titles(embeds)
        assert "Answer." in "".join(embed.description or "" for embed in embeds)
        # The reply ran at standard speed, so it bills at standard rates.
        assert costs == [pytest.approx(STANDARD_COST)]
        # The conversation keeps fast mode for its next turn.
        conversation = cog.conversations[
            (mock_discord_context.author.id, mock_discord_context.channel.id)
        ]
        assert conversation.params.fast is True

    @pytest.mark.parametrize("status", [429, 529])
    async def test_the_fast_attempt_is_not_retried_by_the_sdk(
        self, make_cog, mock_discord_context, status
    ):
        """The client in the bot retries 429 and 5xx. The fast attempt skips those retries:
        the SDK would wait the API's `retry-after` before each one, so the fallback would
        start only after the last retry."""
        api = FakeApi(fast_script=[CAPACITY_ERRORS[status]])
        cog = make_cog(api, max_retries=4)

        embeds, _ = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [status, 200]
        assert [body.get("speed") for body in api.bodies] == ["fast", None]
        assert NOTICE_TITLE in _titles(embeds)

    async def test_the_request_at_standard_speed_keeps_the_normal_retries(
        self, make_cog, mock_discord_context
    ):
        api = FakeApi(
            fast_script=[CAPACITY_ERRORS[429]],
            standard_script=[(500, {"type": "api_error", "message": "Internal error."}), None],
        )
        cog = make_cog(api, max_retries=2)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [429, 500, 200]
        assert [body.get("speed") for body in api.bodies] == ["fast", None, None]
        assert NOTICE_TITLE in _titles(embeds)
        assert costs == [pytest.approx(STANDARD_COST)]

    async def test_a_fast_request_that_succeeds_is_sent_once_and_bills_fast(
        self, make_cog, mock_discord_context
    ):
        api = FakeApi()
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [200]
        assert api.bodies[0]["speed"] == "fast"
        assert NOTICE_TITLE not in _titles(embeds)
        assert costs == [pytest.approx(2 * STANDARD_COST)]

    async def test_the_declined_attempt_of_a_refusal_fallback_is_billed_at_standard_speed(
        self, make_cog, mock_discord_context
    ):
        """The resent request is answered by the fallback model after a refusal. The first
        attempt is in usage.iterations and is billed at the speed that ran: standard."""
        iterations = [
            {"type": "message", "model": MODEL, **COUNTS},
            {"type": "fallback_message", "model": FALLBACK_TARGET, **COUNTS},
        ]
        api = FakeApi(
            fast_script=[CAPACITY_ERRORS[429]],
            standard_usage=_usage(
                "standard",
                {
                    "input_tokens": 2000,
                    "output_tokens": 200,
                    "cache_creation_input_tokens": 400,
                    "cache_read_input_tokens": 600,
                },
            )
            | {"iterations": iterations},
        )
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [429, 200]
        assert NOTICE_TITLE in _titles(embeds)
        assert costs == [pytest.approx(STANDARD_COST + FALLBACK_COST)]

    async def test_speed_stays_off_for_the_rest_of_a_tool_loop(self, make_cog):
        """Request 1 runs fast and asks for a tool; request 2 gets a 429 and is sent again
        at standard speed and asks for another tool; request 4 answers. Requests after the
        fallback do not try fast again, and each request bills at the speed it ran."""
        api = ToolLoopApi()
        cog = make_cog(api)
        cog._execute_tool = AsyncMock(return_value="empty")
        messages = [{"role": "user", "content": "Question"}]
        api_params = build_api_params(
            ChatCompletionParameters(model=MODEL, fast=True, tools=["memory"]), messages
        )

        parsed = await call_api_with_tool_loop(
            cog, api_params=api_params, messages=messages, user_id=1
        )

        assert api.statuses == [200, 429, 200, 200]
        assert [body.get("speed") for body in api.bodies] == ["fast", "fast", None, None]
        assert parsed.text == "Done."
        assert parsed.fast_mode_unavailable is True
        request_cost, _ = cog._track_daily_cost(1, MODEL, parsed)
        # The first request ran fast (2x); the three that ran after the fallback did not.
        assert request_cost == pytest.approx(2 * STANDARD_COST + 2 * STANDARD_COST)

    async def test_a_follow_up_that_gets_a_capacity_error_shows_the_notice(
        self, make_cog, mock_discord_context, mock_discord_message
    ):
        """The follow-up path builds its own reply: the first turn runs fast, the second
        gets a 529 and runs at standard speed."""
        api = FakeApi(fast_script=[None, CAPACITY_ERRORS[529]])
        cog = make_cog(api)
        await _chat(cog, mock_discord_context, fast=True)
        costs = _record_costs(cog)
        message = mock_discord_message
        message.author = mock_discord_context.author
        message.stickers = []
        message.reply = AsyncMock(return_value=MagicMock(id=456))
        conversation = cog.conversations[
            (mock_discord_context.author.id, mock_discord_context.channel.id)
        ]

        with patch("discord_claude.cogs.claude.chat.keep_typing", AsyncMock()):
            await cog.handle_new_message_in_conversation(message, conversation)

        embeds = _embeds_sent(message.reply)
        assert api.statuses == [200, 529, 200]
        assert [body.get("speed") for body in api.bodies] == ["fast", "fast", None]
        assert _titles(embeds).count(NOTICE_TITLE) == 1
        assert "Error" not in _titles(embeds)
        assert costs == [pytest.approx(STANDARD_COST)]
        assert conversation.params.fast is True


class TestFastRetryableErrors:
    """The fast attempt skips the SDK's retries, so an error the SDK would retry is sent
    once more through the normal client at the same speed."""

    @pytest.mark.parametrize(
        "failure",
        [
            (408, {"type": "api_error", "message": "Request timeout."}),
            (409, {"type": "api_error", "message": "Conflict."}),
            (500, {"type": "api_error", "message": "Internal server error."}),
            (503, {"type": "api_error", "message": "Service unavailable."}),
            CONNECTION_ERROR,
        ],
        ids=["408", "409", "500", "503", "connection"],
    )
    async def test_the_request_is_sent_again_at_fast_speed(
        self, make_cog, mock_discord_context, failure
    ):
        api = FakeApi(fast_script=[failure, None])
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [failure if failure == CONNECTION_ERROR else failure[0], 200]
        assert [body.get("speed") for body in api.bodies] == ["fast", "fast"]
        assert NOTICE_TITLE not in _titles(embeds)
        assert "Error" not in _titles(embeds)
        assert costs == [pytest.approx(2 * STANDARD_COST)]

    async def test_the_second_fast_attempt_has_the_normal_retries(
        self, make_cog, mock_discord_context
    ):
        server_error = (500, {"type": "api_error", "message": "Internal server error."})
        api = FakeApi(fast_script=[server_error, server_error, None])
        cog = make_cog(api, max_retries=2)

        embeds, _ = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [500, 500, 200]
        assert [body.get("speed") for body in api.bodies] == ["fast"] * 3
        assert NOTICE_TITLE not in _titles(embeds)

    async def test_a_capacity_error_on_the_second_fast_attempt_falls_back(
        self, make_cog, mock_discord_context
    ):
        server_error = (500, {"type": "api_error", "message": "Internal server error."})
        api = FakeApi(fast_script=[server_error, CAPACITY_ERRORS[429]])
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [500, 429, 200]
        assert [body.get("speed") for body in api.bodies] == ["fast", "fast", None]
        assert NOTICE_TITLE in _titles(embeds)
        assert costs == [pytest.approx(STANDARD_COST)]

    async def test_an_error_the_sdk_would_not_retry_is_raised_at_once(
        self, make_cog, mock_discord_context
    ):
        server_error = (
            500,
            {"type": "api_error", "message": "Internal server error."},
            {"x-should-retry": "false"},
        )
        api = FakeApi(fast_script=[server_error])
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [500]
        assert _titles(embeds) == ["Error"]
        assert costs == []


class TestOtherErrorsAreNotResentAtStandardSpeed:
    @pytest.mark.parametrize(
        ("status", "error"),
        [
            (400, {"type": "invalid_request_error", "message": "max_tokens: too large"}),
            (401, {"type": "authentication_error", "message": "invalid x-api-key"}),
        ],
    )
    async def test_a_fast_request_with_a_non_retryable_error_fails_as_before(
        self, make_cog, mock_discord_context, status, error
    ):
        api = FakeApi(fast_script=[(status, error)])
        cog = make_cog(api, max_retries=4)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [status]
        assert _titles(embeds) == ["Error"]
        assert error["message"] in embeds[0].description
        assert f"Status: {status}" in embeds[0].description
        assert costs == []
        assert (mock_discord_context.author.id, mock_discord_context.channel.id) not in (
            cog.conversations
        )

    @pytest.mark.parametrize(
        "failure",
        [
            _error(429, "The contract spend limit was reached.", "contract_spend_limit_reached"),
            _error(429, "The monthly spend limit was reached.", "enforced_spend_limit_reached"),
            _error(429, "The request would exceed a ramp limit.", "ramp_limit_exceeded"),
            _error(529, "Compaction is unavailable.", "compaction_unavailable"),
        ],
        ids=["contract-spend-limit", "enforced-spend-limit", "ramp-limit", "compaction"],
    )
    async def test_an_error_with_its_own_code_is_not_a_fast_capacity_error(
        self, make_cog, mock_discord_context, failure
    ):
        """Such an error names another cause, so the reply is not sent at standard speed and
        the notice is not shown. The SDK retries it at the same speed, as it did before."""
        status, error = failure
        api = FakeApi(fast_script=[failure])
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [status, status]
        assert [body.get("speed") for body in api.bodies] == ["fast", "fast"]
        assert _titles(embeds) == ["Error"]
        assert error["message"] in embeds[0].description
        assert f"Status: {status}" in embeds[0].description
        assert costs == []

    async def test_a_429_at_standard_speed_is_not_retried_at_another_speed(
        self, make_cog, mock_discord_context
    ):
        api = FakeApi(standard_script=[CAPACITY_ERRORS[429]])
        cog = make_cog(api)

        embeds, costs = await _chat(cog, mock_discord_context)

        assert api.statuses == [429]
        assert _titles(embeds) == ["Error"]
        assert "Status: 429" in embeds[0].description
        assert costs == []

    async def test_a_second_capacity_error_is_not_retried(self, make_cog, mock_discord_context):
        """The resend is the last attempt: when standard speed fails too, the error is shown."""
        api = FakeApi(fast_script=[CAPACITY_ERRORS[529]], standard_script=[CAPACITY_ERRORS[529]])
        cog = make_cog(api)

        embeds, _ = await _chat(cog, mock_discord_context, fast=True)

        assert api.statuses == [529, 529]
        assert _titles(embeds) == ["Error"]
        assert "Status: 529" in embeds[0].description
