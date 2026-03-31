class TestToolChoiceSupport:
    """Tests for tool_choice request handling and validation."""

    def test_build_api_params_omits_tool_choice_by_default(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-haiku-4-5", tools=["web_search"])

        api_params = ClaudeCog._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert "tool_choice" not in api_params

    def test_build_api_params_includes_explicit_none(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            tools=["web_search"],
            tool_choice={"type": "none"},
        )

        api_params = ClaudeCog._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert api_params["tool_choice"] == {"type": "none"}
        assert api_params["tools"][0]["name"] == "web_search"

    def test_build_api_params_omits_tool_choice_when_no_tools(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            tools=[],
            tool_choice={"type": "auto"},
        )

        api_params = ClaudeCog._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert "tool_choice" not in api_params
        assert "tools" not in api_params

    def test_validate_request_configuration_rejects_forced_any_with_thinking(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-opus-4-6",
            tools=["web_search"],
            tool_choice={"type": "any"},
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "Thinking mode only supports tool behavior `auto` or `none`" in error

    def test_validate_request_configuration_rejects_forced_tool_with_thinking(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            thinking_budget=5000,
            tools=["memory"],
            tool_choice={"type": "tool", "name": "memory"},
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "Thinking mode only supports tool behavior `auto` or `none`" in error
