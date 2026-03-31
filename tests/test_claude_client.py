class TestClaudeCogIntegration:
    """Integration tests for the Anthropic API client (mocked)."""

    async def test_messages_create_basic(self, mock_anthropic_client):
        """Test basic message creation with the Anthropic API."""
        response = await mock_anthropic_client.messages.create(
            model="claude-sonnet-4",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello, Claude!"}],
        )

        assert response.content[0].text == "Hello! How can I help you today?"
        assert response.id.startswith("msg_")
        mock_anthropic_client.messages.create.assert_called_once()

    async def test_messages_create_with_system(self, mock_anthropic_client):
        """Test message creation with system prompt."""
        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4",
            max_tokens=1024,
            system="You are a helpful assistant.",
            messages=[{"role": "user", "content": "What is 2+2?"}],
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are a helpful assistant."

    async def test_messages_create_with_temperature(self, mock_anthropic_client):
        """Test message creation with temperature parameter."""
        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4",
            max_tokens=1024,
            temperature=0.7,
            messages=[{"role": "user", "content": "Be creative!"}],
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7

    async def test_messages_create_multi_turn(self, mock_anthropic_client):
        """Test multi-turn conversation."""
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4",
            max_tokens=1024,
            messages=messages,
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert len(call_kwargs["messages"]) == 3

    async def test_messages_create_with_image_content(self, mock_anthropic_client):
        """Test message creation with image content block."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                        },
                    },
                    {"type": "text", "text": "What's in this image?"},
                ],
            }
        ]

        await mock_anthropic_client.messages.create(
            model="claude-sonnet-4",
            max_tokens=1024,
            messages=messages,
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["messages"][0]["content"][0]["type"] == "image"
        assert call_kwargs["messages"][0]["content"][1]["type"] == "text"
