from discord_claude.cogs.claude.tool_registry import (
    TOOL_REGISTRY,
    get_anthropic_tools,
    get_tool_select_options,
)


class TestToolRegistry:
    """Structural integrity checks on the TOOL_REGISTRY entries."""

    def test_all_keys_match_entry_ids(self):
        """Each registry key matches the id field of its entry."""
        for key, entry in TOOL_REGISTRY.items():
            assert entry.id == key

    def test_client_tools_have_handler_key(self):
        """Every client-mode tool must declare a handler_key."""
        for entry in TOOL_REGISTRY.values():
            if entry.execution_mode == "client":
                assert entry.handler_key is not None, (
                    f"client tool '{entry.id}' is missing handler_key"
                )

    def test_server_tools_have_no_handler_key(self):
        """Server-mode tools should not declare a handler_key."""
        for entry in TOOL_REGISTRY.values():
            if entry.execution_mode == "server":
                assert entry.handler_key is None, (
                    f"server tool '{entry.id}' should not have handler_key"
                )

    def test_all_anthropic_tools_have_name(self):
        """Every Anthropic tool payload must include a name field."""
        for entry in TOOL_REGISTRY.values():
            assert "name" in entry.anthropic_tool, (
                f"tool '{entry.id}' anthropic_tool missing 'name'"
            )

    def test_memory_is_client_mode(self):
        assert TOOL_REGISTRY["memory"].execution_mode == "client"
        assert TOOL_REGISTRY["memory"].handler_key == "memory"

    def test_server_tools_are_server_mode(self):
        for tool_id in ("web_search", "web_fetch", "code_execution"):
            assert TOOL_REGISTRY[tool_id].execution_mode == "server"


class TestGetAnthropicTools:
    """Tests for get_anthropic_tools()."""

    def test_returns_payloads_for_known_ids(self):
        result = get_anthropic_tools(["memory", "web_search"])
        assert len(result) == 2
        names = {t["name"] for t in result}
        assert names == {"memory", "web_search"}

    def test_skips_unknown_ids(self):
        result = get_anthropic_tools(["memory", "nonexistent"])
        assert len(result) == 1
        assert result[0]["name"] == "memory"

    def test_empty_list_returns_empty(self):
        assert get_anthropic_tools([]) == []

    def test_all_unknown_returns_empty(self):
        assert get_anthropic_tools(["bogus", "also_bogus"]) == []

    def test_preserves_payload_fields(self):
        """Payloads are returned as-is from the registry."""
        result = get_anthropic_tools(["web_search"])
        assert result[0]["max_uses"] == 5

    def test_order_follows_input(self):
        result = get_anthropic_tools(["code_execution", "memory"])
        assert result[0]["name"] == "code_execution"
        assert result[1]["name"] == "memory"


class TestGetToolSelectOptions:
    """Tests for get_tool_select_options()."""

    def test_returns_one_option_per_registry_entry(self):
        options = get_tool_select_options(set())
        assert len(options) == len(TOOL_REGISTRY)

    def test_selected_tools_have_default_true(self):
        options = get_tool_select_options({"memory", "web_search"})
        by_value = {o["value"]: o for o in options}
        assert by_value["memory"]["default"] is True
        assert by_value["web_search"]["default"] is True

    def test_unselected_tools_have_default_false(self):
        options = get_tool_select_options({"memory"})
        by_value = {o["value"]: o for o in options}
        assert by_value["web_search"]["default"] is False
        assert by_value["code_execution"]["default"] is False

    def test_empty_selection_all_default_false(self):
        options = get_tool_select_options(set())
        assert all(not o["default"] for o in options)

    def test_option_shape(self):
        """Each option has the four keys SelectOption expects."""
        options = get_tool_select_options(set())
        for option in options:
            assert set(option.keys()) == {"label", "value", "description", "default"}

    def test_values_match_registry_ids(self):
        options = get_tool_select_options(set())
        values = {o["value"] for o in options}
        assert values == set(TOOL_REGISTRY.keys())
