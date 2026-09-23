from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_claude.cogs.claude.state import _copy_messages_without_advisor_blocks


class TestCompactConversation:
    async def test_uses_text_fallback_when_structured_summary_missing(self):
        from discord_claude.cogs.claude.state import compact_conversation

        response = MagicMock()
        response.parsed_output = None
        response.content = [MagicMock(text="Fallback continuation summary.")]

        cog = MagicMock()
        cog.client.messages.parse = AsyncMock(return_value=response)
        cog.logger = MagicMock()

        messages = [{"role": "user", "content": "Earlier request"}]

        summary = await compact_conversation(cog, messages)

        assert summary == "<summary>\nFallback continuation summary.\n</summary>"
        assert messages == [{"role": "user", "content": summary}]
        cog.logger.warning.assert_called_once()


class TestCompactionSummaryUsage:
    async def test_summarizer_usage_is_added_to_the_given_totals(self):
        from discord_claude.cogs.claude.state import compact_conversation
        from discord_claude.util import COMPACTION_SUMMARY_MODEL, ModelTokenUsage, UsageTotals

        response = MagicMock()
        response.parsed_output = None
        response.content = [MagicMock(text="Summary.")]
        response.usage = MagicMock(
            input_tokens=40_000,
            output_tokens=900,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
            output_tokens_details=None,
        )
        cog = MagicMock()
        cog.client.messages.parse = AsyncMock(return_value=response)
        totals = UsageTotals()

        await compact_conversation(cog, [{"role": "user", "content": "x"}], usage_totals=totals)

        assert totals.tokens_by_model == {
            COMPACTION_SUMMARY_MODEL: ModelTokenUsage(40_000, 900, 0, 0)
        }


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
