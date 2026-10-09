from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_claude.cogs.claude.state import _copy_messages_without_advisor_blocks

SUMMARY_JSON = '{"task": "t", "key_context": "k", "current_state": "c", "next_steps": "n"}'


def _summary_response(text=SUMMARY_JSON, stop_reason="end_turn", usage=None):
    """A summarizer response holding one text block (none when ``text`` is None)."""
    response = MagicMock()
    response.content = [] if text is None else [MagicMock(type="text", text=text)]
    response.stop_reason = stop_reason
    response.usage = usage
    return response


def _usage(input_tokens, output_tokens=0, cache_read_input_tokens=0):
    return MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=cache_read_input_tokens,
        output_tokens_details=None,
    )


class TestCompactConversation:
    @staticmethod
    def _cog(response):
        cog = MagicMock()
        cog.client.messages.create = AsyncMock(return_value=response)
        cog.logger = MagicMock()
        return cog

    async def test_replaces_history_with_the_structured_summary(self):
        from discord_claude.cogs.claude.state import ConversationSummary, compact_conversation

        cog = self._cog(_summary_response())
        messages = [{"role": "user", "content": "Earlier request"}]

        summary = await compact_conversation(cog, messages)

        assert summary == ConversationSummary.model_validate_json(SUMMARY_JSON).to_message_text()
        assert messages == [{"role": "user", "content": summary}]

    @pytest.mark.parametrize(
        ("stop_reason", "text"),
        [
            ("refusal", None),
            ("refusal", ""),
            ("refusal", "I can't help summarize this."),
            ("refusal", '{"task": "Plan a tr'),
            ("max_tokens", '{"task": "t", "key_context": "k", "current_st'),
            ("end_turn", None),
        ],
    )
    async def test_keeps_history_and_bills_when_no_valid_summary(self, stop_reason, text):
        """A response whose text is not a valid ConversationSummary (a refusal with no
        text, empty text, prose or partial JSON, JSON cut off at max_tokens, an empty
        response) keeps the history, and its usage is billed."""
        from discord_claude.cogs.claude.state import compact_conversation
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, ModelTokenUsage, UsageTotals

        cog = self._cog(_summary_response(text, stop_reason, _usage(2_000, 30)))
        messages = [
            {"role": "user", "content": "Earlier request"},
            {"role": "assistant", "content": "Earlier answer"},
        ]
        original = [dict(message) for message in messages]
        totals = UsageTotals(request_model="claude-haiku-4-5")

        summary = await compact_conversation(cog, messages, usage_totals=totals)

        assert summary is None
        assert messages == original
        assert totals.tokens_by_model == {
            COMPACTION_SUMMARY_MODEL: ModelTokenUsage(input_tokens=2_000, output_tokens=30)
        }
        cog.logger.warning.assert_called_once()

    async def test_keeps_history_when_the_summarizer_call_raises(self):
        """An APIError (the call itself failed) keeps the history and bills nothing,
        because no response came back."""
        from anthropic import APIConnectionError

        from discord_claude.cogs.claude.state import compact_conversation
        from discord_claude.util import UsageTotals

        cog = MagicMock()
        cog.client.messages.create = AsyncMock(side_effect=APIConnectionError(request=MagicMock()))
        cog.logger = MagicMock()
        messages = [
            {"role": "user", "content": "Earlier request"},
            {"role": "assistant", "content": "Earlier answer"},
        ]
        original = [dict(message) for message in messages]
        totals = UsageTotals()

        summary = await compact_conversation(cog, messages, usage_totals=totals)

        assert summary is None
        assert messages == original
        assert totals.tokens_by_model == {}
        cog.logger.warning.assert_called_once()


class TestCompactionSummaryUsage:
    async def test_summarizer_usage_is_added_to_the_given_totals(self):
        from discord_claude.cogs.claude.state import compact_conversation
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, ModelTokenUsage, UsageTotals

        cog = MagicMock()
        cog.client.messages.create = AsyncMock(
            return_value=_summary_response(usage=_usage(40_000, 900))
        )
        totals = UsageTotals()

        await compact_conversation(cog, [{"role": "user", "content": "x"}], usage_totals=totals)

        assert totals.tokens_by_model == {
            COMPACTION_SUMMARY_MODEL: ModelTokenUsage(40_000, 900, 0, 0)
        }

    async def test_summarizer_call_disables_thinking_without_fallbacks_or_effort(self):
        """Haiku 5.5 thinks by default and its thinking tokens count against max_tokens,
        so the call disables thinking. It rejects `fallbacks`, and disabled thinking is
        accepted only at effort high or below, so neither is sent. The schema goes in
        output_config.format, the form messages.parse(output_format=...) sends."""
        from anthropic import transform_schema

        from discord_claude.cogs.claude.state import ConversationSummary, compact_conversation
        from discord_claude.util import COMPACTION_SUMMARY_MODEL

        cog = MagicMock()
        cog.client.messages.create = AsyncMock(return_value=_summary_response())

        await compact_conversation(cog, [{"role": "user", "content": "x"}], system="Be brief.")

        kwargs = cog.client.messages.create.call_args.kwargs
        assert COMPACTION_SUMMARY_MODEL == "claude-haiku-5-5"
        assert kwargs["model"] == COMPACTION_SUMMARY_MODEL
        assert kwargs["max_tokens"] == 4096
        assert kwargs["output_config"] == {
            "format": {"type": "json_schema", "schema": transform_schema(ConversationSummary)}
        }
        assert kwargs["thinking"] == {"type": "disabled"}
        assert kwargs["system"] == "Be brief."
        assert "fallbacks" not in kwargs
        assert "effort" not in kwargs["output_config"]
        assert "tools" not in kwargs
        assert "betas" not in kwargs

    async def test_summarizer_refusal_keeps_history_and_is_billed(self):
        """A summarizer refusal written as prose keeps the history. Its usage is still
        billed: the bot bills every declined attempt because the API does not report
        which refusal categories are billed."""
        from discord_claude.cogs.claude.state import compact_conversation
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, ModelTokenUsage, UsageTotals

        cog = MagicMock()
        cog.client.messages.create = AsyncMock(
            return_value=_summary_response(
                "I can't help summarize this.", "refusal", _usage(2_000, 12)
            )
        )
        messages = [
            {"role": "user", "content": "Earlier request"},
            {"role": "assistant", "content": "Earlier answer"},
        ]
        original = [dict(message) for message in messages]
        totals = UsageTotals(request_model="claude-haiku-4-5")

        summary = await compact_conversation(cog, messages, usage_totals=totals)

        assert summary is None
        assert messages == original
        assert totals.tokens_by_model == {
            COMPACTION_SUMMARY_MODEL: ModelTokenUsage(input_tokens=2_000, output_tokens=12)
        }

    async def test_summarizer_receives_thinking_blocks_unchanged(self):
        """Thinking and redacted_thinking blocks of earlier turns stay in the copy
        sent to the summarizer. Only the advisor blocks are removed."""
        from discord_claude.cogs.claude.state import compact_conversation

        thinking = {"type": "thinking", "thinking": "391 = 17 x 23.", "signature": "sig"}
        redacted = {"type": "redacted_thinking", "data": "opaque"}
        advisor_call = {"type": "server_tool_use", "id": "srvtoolu_01", "name": "advisor"}
        answer = {"type": "text", "text": "No, 391 is 17 x 23."}
        cog = MagicMock()
        cog.client.messages.create = AsyncMock(return_value=_summary_response())

        await compact_conversation(
            cog,
            [
                {"role": "user", "content": "Is 391 prime?"},
                {"role": "assistant", "content": [thinking, redacted, advisor_call, answer]},
                {"role": "user", "content": "And 397?"},
            ],
        )

        sent = cog.client.messages.create.call_args.kwargs["messages"]
        assert sent[1]["content"] == [thinking, redacted, answer]

    @pytest.mark.parametrize(
        ("prompt_tokens", "long_context", "input_price", "output_price"),
        [
            # A conversation at the 150k manual trigger: over 100,000 summarizer tokens.
            (150_000, True, 0.50, 2.50),
            (20_000, False, 0.10, 0.50),
        ],
    )
    async def test_summarizer_call_bills_at_the_price_tier_of_its_prompt(
        self, prompt_tokens, long_context, input_price, output_price
    ):
        """The summary call is one request, priced by its own prompt size: Haiku 5.5's
        long-context tier over 100,000 tokens, its standard prices below."""
        from discord_claude.cogs.claude.responses import ParsedResponse
        from discord_claude.cogs.claude.state import compact_conversation, track_daily_cost
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, ModelTokenUsage, UsageTotals

        # Half of the prompt is a cache read: the tier counts the full prompt.
        response = _summary_response(
            usage=_usage(
                prompt_tokens // 2,
                output_tokens=1_000,
                cache_read_input_tokens=prompt_tokens // 2,
            )
        )
        cog = MagicMock()
        cog.daily_costs = {}
        cog.client.messages.create = AsyncMock(return_value=response)
        totals = UsageTotals(request_model="claude-opus-4-5")

        await compact_conversation(cog, [{"role": "user", "content": "x"}], usage_totals=totals)
        parsed = ParsedResponse()
        totals.apply_to(parsed, context_window=200_000)
        cost, _ = track_daily_cost(cog, 1, "claude-opus-4-5", parsed)

        tokens = ModelTokenUsage(prompt_tokens // 2, 1_000, 0, prompt_tokens // 2)
        expected_groups = {COMPACTION_SUMMARY_MODEL: tokens}
        if long_context:
            assert parsed.long_context_tokens_by_model == expected_groups
            assert parsed.tokens_by_model == {}
        else:
            assert parsed.tokens_by_model == expected_groups
            assert parsed.long_context_tokens_by_model == {}
        assert cost == pytest.approx(
            (
                prompt_tokens // 2 * input_price
                + prompt_tokens // 2 * input_price * 0.10
                + 1_000 * output_price
            )
            / 1e6
        )


class TestTrackDailyCost:
    """Cost of one turn: every token group at the rates of the model that produced it."""

    @staticmethod
    def _cog():
        cog = MagicMock()
        cog.daily_costs = {}
        return cog

    def test_each_model_bills_at_its_own_rates(self):
        from discord_claude.cogs.claude.responses import ParsedResponse
        from discord_claude.cogs.claude.state import track_daily_cost
        from discord_claude.util import ModelTokenUsage

        parsed = ParsedResponse(
            input_tokens=2_000_000,
            output_tokens=1_000_000,
            served_model="claude-opus-4-8",
            tokens_by_model={
                # The declined attempt: $4/MTok input on Opus 5.5.
                "claude-opus-5-5": ModelTokenUsage(input_tokens=1_000_000),
                # The fallback answer: $5 input + $25 output on Opus 4.8.
                "claude-opus-4-8": ModelTokenUsage(input_tokens=1_000_000, output_tokens=1_000_000),
            },
            web_search_requests=2,
        )

        cost, daily = track_daily_cost(self._cog(), 1, "claude-opus-5-5", parsed)

        assert cost == pytest.approx(4.0 + 5.0 + 25.0 + 0.02)
        assert daily == pytest.approx(cost)

    def test_none_key_bills_at_the_request_model(self):
        from discord_claude.cogs.claude.responses import ParsedResponse
        from discord_claude.cogs.claude.state import track_daily_cost
        from discord_claude.util import ModelTokenUsage

        parsed = ParsedResponse(
            input_tokens=1_000_000,
            tokens_by_model={None: ModelTokenUsage(input_tokens=1_000_000)},
        )

        cost, _ = track_daily_cost(self._cog(), 1, "claude-opus-5-5", parsed)

        assert cost == pytest.approx(4.0)

    def test_long_context_group_bills_at_the_tier_prices(self):
        """Haiku 5.5: one request under the threshold at $0.10 input, one over it at $0.50
        input and $2.50 output."""
        from discord_claude.cogs.claude.responses import ParsedResponse
        from discord_claude.cogs.claude.state import track_daily_cost
        from discord_claude.util import ModelTokenUsage

        parsed = ParsedResponse(
            input_tokens=2_000_000,
            output_tokens=1_000_000,
            tokens_by_model={None: ModelTokenUsage(input_tokens=1_000_000)},
            long_context_tokens_by_model={
                None: ModelTokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
            },
        )

        cost, _ = track_daily_cost(self._cog(), 1, "claude-haiku-5-5", parsed)

        assert cost == pytest.approx(0.10 + 0.50 + 2.50)

    def test_a_turn_entirely_in_the_long_context_tier_is_billed_once(self):
        """An empty standard group must not fall back to billing the totals as well."""
        from discord_claude.cogs.claude.responses import ParsedResponse
        from discord_claude.cogs.claude.state import track_daily_cost
        from discord_claude.util import ModelTokenUsage

        parsed = ParsedResponse(
            input_tokens=1_000_000,
            long_context_tokens_by_model={None: ModelTokenUsage(input_tokens=1_000_000)},
        )

        cost, _ = track_daily_cost(self._cog(), 1, "claude-haiku-5-5", parsed)

        assert cost == pytest.approx(0.50)

    def test_totals_without_a_breakdown_bill_at_the_served_model(self):
        from discord_claude.cogs.claude.responses import ParsedResponse
        from discord_claude.cogs.claude.state import track_daily_cost

        parsed = ParsedResponse(input_tokens=1_000_000, served_model="claude-opus-4-8")

        cost, _ = track_daily_cost(self._cog(), 1, "claude-opus-5-5", parsed)

        assert cost == pytest.approx(5.0)


class TestAdvisorHistorySanitization:
    """Tests for stripping advisor-only blocks before manual compaction."""

    def test_copy_messages_without_advisor_blocks(self):
        messages = [
            {"role": "user", "content": "hello"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {
                        "type": "server_tool_use",
                        "id": "srvtoolu_123",
                        "name": "advisor",
                        "input": {},
                    },
                    {
                        "type": "advisor_tool_result",
                        "tool_use_id": "srvtoolu_123",
                        "content": {
                            "type": "advisor_result",
                            "text": "Use a queue.",
                        },
                    },
                    {"type": "text", "text": "Here is the answer."},
                ],
            },
        ]

        sanitized = _copy_messages_without_advisor_blocks(messages)

        assert sanitized[0] == messages[0]
        assert sanitized[1]["role"] == "assistant"
        assert sanitized[1]["content"] == [
            {"type": "text", "text": "Let me check."},
            {"type": "text", "text": "Here is the answer."},
        ]


class TestClaudePruneRuntimeState:
    """Tests for prune_runtime_state — TTL eviction, overflow cap, cascade cleanup."""

    @pytest.fixture
    def cog(self, mock_bot):
        from discord_claude import ClaudeCog

        return ClaudeCog(bot=mock_bot)

    def _make_conversation(self, *, starter=None, age: timedelta = timedelta(0)):
        from discord_claude.util import ChatCompletionParameters, Conversation

        params = ChatCompletionParameters(
            model="claude-opus-4-7",
            conversation_starter=starter,
        )
        conversation = Conversation(params=params, messages=[])
        conversation.updated_at = datetime.now(UTC) - age
        return conversation

    async def test_drops_conversations_older_than_ttl(self, cog):
        from discord_claude.cogs.claude.state import CONVERSATION_TTL, prune_runtime_state

        user = MagicMock(spec=["id"])
        user.id = 42
        cog.conversations[(42, 1)] = self._make_conversation(starter=user, age=CONVERSATION_TTL * 2)
        cog.conversations[(42, 2)] = self._make_conversation(starter=user, age=timedelta(minutes=5))

        await prune_runtime_state(cog)

        assert (42, 1) not in cog.conversations
        assert (42, 2) in cog.conversations

    async def test_overflow_cap_drops_oldest(self, cog, monkeypatch):
        from discord_claude.cogs.claude import state as state_mod
        from discord_claude.cogs.claude.state import prune_runtime_state

        monkeypatch.setattr(state_mod, "MAX_ACTIVE_CONVERSATIONS", 2)
        for i in range(4):
            cog.conversations[(1, i)] = self._make_conversation(age=timedelta(minutes=i))

        await prune_runtime_state(cog)

        assert len(cog.conversations) == 2
        assert {(1, 0), (1, 1)} == set(cog.conversations)

    async def test_cascade_cleans_view_for_pruned_conversation(self, cog):
        from discord_claude.cogs.claude.state import CONVERSATION_TTL, prune_runtime_state

        user = MagicMock(spec=["id"])
        user.id = 99
        cog.conversations[(99, 5)] = self._make_conversation(starter=user, age=CONVERSATION_TTL * 2)

        mock_view = MagicMock()
        cog.views[user] = mock_view
        mock_message = AsyncMock()
        cog.last_view_messages[user] = mock_message

        await prune_runtime_state(cog)

        assert user not in cog.views
        assert user not in cog.last_view_messages

    async def test_prunes_daily_costs_older_than_retention(self, cog):
        from discord_claude.cogs.claude.state import (
            DAILY_COST_RETENTION_DAYS,
            prune_runtime_state,
        )

        old_date = (datetime.now(UTC) - timedelta(days=DAILY_COST_RETENTION_DAYS + 2)).date()
        fresh_date = datetime.now(UTC).date()
        cog.daily_costs[(1, old_date.isoformat())] = (10.0, datetime.now(UTC))
        cog.daily_costs[(1, fresh_date.isoformat())] = (5.0, datetime.now(UTC))

        await prune_runtime_state(cog)

        assert (1, old_date.isoformat()) not in cog.daily_costs
        assert (1, fresh_date.isoformat()) in cog.daily_costs


class TestConversationTouch:
    def test_touch_advances_updated_at(self):
        from discord_claude.util import ChatCompletionParameters, Conversation

        conv = Conversation(
            params=ChatCompletionParameters(model="claude-opus-4-7"),
            messages=[],
        )
        original = conv.updated_at
        conv.updated_at = original - timedelta(hours=1)
        conv.touch()
        assert conv.updated_at > original - timedelta(seconds=1)
