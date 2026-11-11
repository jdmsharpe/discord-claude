import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import pytest
from anthropic import AsyncAnthropic

from discord_claude.cogs.claude.chat import build_api_params, validate_request_configuration
from discord_claude.cogs.claude.command_options import CHAT_MODEL_CHOICES
from discord_claude.cogs.claude.responses import ParsedResponse
from discord_claude.cogs.claude.state import track_daily_cost
from discord_claude.util import ChatCompletionParameters, UsageTotals, calculate_cost


@pytest.mark.parametrize("model", [choice.value for choice in CHAT_MODEL_CHOICES])
async def test_every_chat_model_omits_sampling_on_the_sdk_wire(model):
    def receive(request):
        body = json.loads(request.content)
        assert not {"temperature", "top_p", "top_k"} & body.keys()
        assert request.headers["anthropic-version"] == "2026-10-21"
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    async with AsyncAnthropic(
        api_key="test-only", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(receive))
    ) as client:
        params = build_api_params(
            ChatCompletionParameters(model=model), [{"role": "user", "content": "hi"}]
        )
        await client.messages.create(**params)


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-fable-5-2"])
def test_fast_is_opt_in_and_gated_to_supported_models(model):
    standard = ChatCompletionParameters(model=model)
    fast = ChatCompletionParameters(model=model, fast=True)
    assert "speed" not in build_api_params(standard, [])
    assert build_api_params(fast, [])["speed"] == "fast"
    assert validate_request_configuration(fast) is None
    assert validate_request_configuration(
        ChatCompletionParameters(model="claude-haiku-5-5", fast=True)
    )


@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-fable-5-2"])
@pytest.mark.parametrize("speed,multiplier", [("fast", 2), ("standard", 1), (None, 1)])
def test_fast_billing_uses_served_speed_and_preserves_other_model_rates(model, speed, multiplier):
    totals = UsageTotals(request_model=model)
    counts = dict(
        input_tokens=1000,
        output_tokens=100,
        cache_creation_input_tokens=200,
        cache_read_input_tokens=300,
    )
    totals.accumulate(
        SimpleNamespace(
            speed=speed,
            iterations=[
                SimpleNamespace(type="message", model=model, **counts),
                SimpleNamespace(type="fallback_message", model="claude-opus-4-8", **counts),
            ],
        )
    )
    parsed = ParsedResponse()
    totals.apply_to(parsed, 1_000_000)
    cog = SimpleNamespace(daily_costs={}, logger=MagicMock())
    cost, daily = track_daily_cost(cog, 123, model, parsed)
    expected = multiplier * calculate_cost(model, 1000, 100, 200, 300)
    expected += calculate_cost("claude-opus-4-8", 1000, 100, 200, 300)
    assert cost == pytest.approx(expected)
    assert daily == pytest.approx(expected)


def test_standard_fallback_does_not_discount_the_original_fast_attempt():
    totals = UsageTotals(request_model="claude-opus-5-5", request_speed="fast")
    totals.accumulate(
        SimpleNamespace(
            speed="standard",
            iterations=[
                SimpleNamespace(type="message", model="claude-opus-5-5", input_tokens=100),
                SimpleNamespace(type="fallback_message", model="claude-opus-4-8", input_tokens=200),
            ],
        )
    )
    assert totals.fast_tokens_by_model["claude-opus-5-5"].input_tokens == 100
    assert totals.tokens_by_model["claude-opus-4-8"].input_tokens == 200
