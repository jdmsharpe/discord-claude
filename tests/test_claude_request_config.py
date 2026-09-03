import pytest


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

    def test_build_api_params_includes_advisor_tool_for_opus_5_executor(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters, get_default_advisor_model

        params = ChatCompletionParameters(
            model="claude-opus-5",
            advisor_model=get_default_advisor_model("claude-opus-5"),
        )

        api_params = ClaudeCog._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert api_params["tools"] == [
            {
                "type": "advisor_20260301",
                "name": "advisor",
                "model": "claude-opus-5",
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

    def test_validate_request_configuration_rejects_sonnet_4_5_advisor_executor(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-sonnet-4-5",
            advisor_model="claude-opus-4-8",
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "Advisor is not supported for `claude-sonnet-4-5`" in error

    def test_validate_request_configuration_accepts_every_documented_advisor_pair(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ADVISOR_MODEL_COMPATIBILITY, ChatCompletionParameters

        for executor, advisors in ADVISOR_MODEL_COMPATIBILITY.items():
            for advisor in advisors:
                params = ChatCompletionParameters(model=executor, advisor_model=advisor)

                assert ClaudeCog._validate_request_configuration(params) is None, (
                    executor,
                    advisor,
                )

    def test_validate_request_configuration_rejects_advisor_outside_executor_pairs(self):
        """Each executor rejects an advisor the docs table does not list for it.

        Opus 5 / Fable 5 only take Opus 5 / Fable 5 / Fable 5.1 advisors and Fable 5.1
        takes only a Fable 5.1 advisor, so the otherwise
        default claude-opus-4-8 must be refused there; the mid-tier executors
        drop the weaker 4.6-generation advisors; and nothing accepts Haiku.
        """
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        cases = [
            ("claude-fable-5-1", "claude-opus-4-8"),
            ("claude-fable-5-1", "claude-opus-5"),
            ("claude-fable-5-1", "claude-fable-5"),
            ("claude-opus-5", "claude-opus-4-8"),
            ("claude-fable-5", "claude-opus-4-8"),
            ("claude-opus-4-8", "claude-opus-4-6"),
            ("claude-opus-4-7", "claude-sonnet-4-6"),
            ("claude-opus-4-6", "claude-sonnet-4-6"),
            ("claude-sonnet-5", "claude-opus-4-6"),
            ("claude-sonnet-4-6", "claude-haiku-4-5"),
            ("claude-haiku-4-5", "claude-haiku-4-5"),
        ]
        for executor, advisor in cases:
            params = ChatCompletionParameters(model=executor, advisor_model=advisor)

            error = ClaudeCog._validate_request_configuration(params)

            assert error is not None, (executor, advisor)
            assert f"Advisor model `{advisor}` is not supported for `{executor}`" in error

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

    def test_validate_request_configuration_rejects_forced_tool_use_on_fable_5_1(self):
        """Fable 5.1 400s on `tool_choice` any/tool (live-probed 2026-09-03), so it is
        refused with a model-specific message ahead of the generic thinking rule."""
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        for tool_choice in ({"type": "any"}, {"type": "tool", "name": "memory"}):
            params = ChatCompletionParameters(
                model="claude-fable-5-1", tools=["memory"], tool_choice=tool_choice
            )
            error = ClaudeCog._validate_request_configuration(params)
            assert error is not None, tool_choice
            assert "does not support forced tool use" in error

        params = ChatCompletionParameters(
            model="claude-fable-5-1", tools=["memory"], tool_choice={"type": "auto"}
        )
        assert ClaudeCog._validate_request_configuration(params) is None

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

    def test_validate_request_configuration_rejects_thinking_budget_for_opus_4_7(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-opus-4-7",
            thinking_budget=5000,
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "only supports adaptive thinking" in error

    def test_validate_request_configuration_rejects_sampling_overrides_for_opus_4_7(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(
            model="claude-opus-4-7",
            temperature=0.7,
        )

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "does not support custom sampling parameters" in error

    def test_validate_request_configuration_rejects_effort_for_haiku_4_5(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-haiku-4-5", effort="low")

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "does not support the `effort` parameter" in error

    def test_validate_request_configuration_rejects_max_effort_for_opus_4_5(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-opus-4-5", effort="max")

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "does not support effort `max`" in error
        assert "`low`, `medium`, `high`." in error
        assert "xhigh" not in error

    def test_validate_request_configuration_rejects_xhigh_effort_for_opus_4_6(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-opus-4-6", effort="xhigh")

        error = ClaudeCog._validate_request_configuration(params)

        assert error is not None
        assert "does not support effort `xhigh`" in error
        assert "`low`, `medium`, `high`, `max`." in error

    def test_validate_request_configuration_accepts_max_effort_for_sonnet_4_6(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-sonnet-4-6", effort="max")

        assert ClaudeCog._validate_request_configuration(params) is None

    def test_validate_request_configuration_accepts_xhigh_effort_for_opus_5(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-opus-5", effort="xhigh")

        assert ClaudeCog._validate_request_configuration(params) is None

    def test_validate_request_configuration_accepts_unset_effort_for_every_model(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.cogs.claude.command_options import CHAT_MODEL_CHOICES
        from discord_claude.util import ChatCompletionParameters

        for choice in CHAT_MODEL_CHOICES:
            params = ChatCompletionParameters(model=choice.value)

            assert ClaudeCog._validate_request_configuration(params) is None, choice.value

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

    def test_build_api_params_nests_effort_under_output_config(self):
        from discord_claude.cogs.claude.cog import ClaudeCog
        from discord_claude.util import ChatCompletionParameters

        params = ChatCompletionParameters(model="claude-opus-4-8", effort="high")

        api_params = ClaudeCog._build_api_params(
            params,
            [{"role": "user", "content": "Hello"}],
        )

        assert "effort" not in api_params
        assert api_params["output_config"] == {"effort": "high"}

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


class TestThinkingDisplay:
    @staticmethod
    def _params(model: str, **kwargs):
        from discord_claude.util import ChatCompletionParameters

        return ChatCompletionParameters(model=model, **kwargs)

    def test_build_thinking_config_defaults_to_summarized_display(self):
        from discord_claude.cogs.claude.chat import build_thinking_config

        assert build_thinking_config(self._params("claude-fable-5-1")) == {
            "type": "adaptive",
            "display": "summarized",
        }

    def test_build_thinking_config_passes_updates_display(self):
        from discord_claude.cogs.claude.chat import (
            build_thinking_config,
            validate_request_configuration,
        )

        params = self._params("claude-fable-5-1", thinking_display="updates")
        assert build_thinking_config(params) == {"type": "adaptive", "display": "updates"}
        assert validate_request_configuration(params) is None

    @pytest.mark.parametrize("model", ["claude-fable-5-1", "claude-fable-5"])
    def test_validate_request_configuration_accepts_updates_display_on_fable(self, model):
        from discord_claude.cogs.claude.chat import validate_request_configuration

        params = self._params(model, thinking_display="updates")
        assert validate_request_configuration(params) is None

    @pytest.mark.parametrize("model", ["claude-opus-5", "claude-sonnet-5", "claude-opus-4-6"])
    def test_validate_request_configuration_rejects_updates_display_elsewhere(self, model):
        """Other adaptive models accept the value but write no progress updates (Opus 5
        probed 2026-09-03), so the option would only hide reasoning — refuse it."""
        from discord_claude.cogs.claude.chat import validate_request_configuration

        error = validate_request_configuration(self._params(model, thinking_display="updates"))
        assert error is not None
        assert "`updates`" in error
        assert "`claude-fable-5-1`" in error
        assert "`claude-fable-5`" in error
