from discord_claude.cogs.claude.state import _copy_messages_without_advisor_blocks


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
