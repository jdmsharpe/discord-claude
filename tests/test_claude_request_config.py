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

    def test_build_api_params_includes_advisor_tool(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-sonnet-4-6",
            advisor_model="claude-opus-4-6",
        )

        api_params = ClaudeCog._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert api_params["tools"] == [
            {
                "type": "advisor_20260301",
                "name": "advisor",
                "model": "claude-opus-4-6",
                "max_uses": 3,
            }
        ]

    def test_validate_request_configuration_rejects_unsupported_advisor_executor(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-opus-4-5",
            advisor_model="claude-opus-4-6",
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "Advisor is not supported" in error

    def test_validate_request_configuration_rejects_tool_choice_none_with_advisor(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-sonnet-4-6",
            advisor_model="claude-opus-4-6",
            tool_choice={"type": "none"},
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "disables advisor calls" in error

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

    def test_build_api_params_includes_mcp_servers(self, monkeypatch):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.config.mcp import AnthropicMcpPreset
        from discord_claude.util import ChatCompletionParameters

        monkeypatch.setenv("CLAUDE_MCP_TOKEN", "secret-token")
        preset = AnthropicMcpPreset(
            name="github",
            server_url="https://mcp.github.com/sse",
            authorization_env_var="CLAUDE_MCP_TOKEN",
            allowed_tools=["search_issues"],
            defer_loading=True,
        )
        monkeypatch.setattr(
            "discord_claude.cogs.claude.chat.resolve_mcp_presets",
            lambda names: ([preset], None),
        )

        params = ChatCompletionParameters(
            model="claude-haiku-4-5",
            tools=["web_search"],
            mcp_preset_names=["github"],
            tool_choice={"type": "auto"},
        )

        api_params = ClaudeCog._build_api_params(params, [{"role": "user", "content": "Hello"}])

        assert api_params["mcp_servers"] == [
            {
                "type": "url",
                "url": "https://mcp.github.com/sse",
                "name": "github",
                "authorization_token": "secret-token",
            }
        ]
        assert api_params["tools"][0]["name"] == "web_search"
        assert api_params["tools"][1]["type"] == "mcp_toolset"
        assert api_params["tools"][1]["mcp_server_name"] == "github"
        assert api_params["tools"][1]["default_config"] == {
            "enabled": False,
            "defer_loading": True,
        }
        assert api_params["tools"][1]["configs"] == {"search_issues": {"enabled": True}}
        assert api_params["tool_choice"] == {"type": "auto"}

    def test_build_api_params_without_mcp_is_unchanged(self, monkeypatch):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        monkeypatch.setattr(
            "discord_claude.cogs.claude.chat.resolve_mcp_presets",
            lambda names: ([], None),
        )

        params = ChatCompletionParameters(model="claude-haiku-4-5", tools=["web_search"])

        api_params = ClaudeCog._build_api_params(params, [{"role": "user", "content": "Hello"}])

        assert "mcp_servers" not in api_params
        assert api_params["tools"] == [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 5,
            }
        ]
