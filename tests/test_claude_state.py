from datetime import datetime, timedelta, timezone
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
        conversation.updated_at = datetime.now(timezone.utc) - age
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

        old_date = (
            datetime.now(timezone.utc) - timedelta(days=DAILY_COST_RETENTION_DAYS + 2)
        ).date()
        fresh_date = datetime.now(timezone.utc).date()
        cog.daily_costs[(1, old_date.isoformat())] = (10.0, datetime.now(timezone.utc))
        cog.daily_costs[(1, fresh_date.isoformat())] = (5.0, datetime.now(timezone.utc))

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
