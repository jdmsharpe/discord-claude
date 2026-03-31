import json

import pytest


class TestAnthropicMcpConfig:
    def test_load_inline_json(self, monkeypatch):
        from discord_claude.config.mcp import load_anthropic_mcp_presets

        monkeypatch.setenv(
            "ANTHROPIC_MCP_PRESETS_JSON",
            json.dumps(
                {
                    "github": {
                        "url": "https://mcp.github.com/sse",
                        "allowed_tools": ["search_issues", "search_issues"],
                        "defer_loading": True,
                    }
                }
            ),
        )
        monkeypatch.delenv("ANTHROPIC_MCP_PRESETS_PATH", raising=False)

        presets = load_anthropic_mcp_presets()

        assert presets["github"].server_url == "https://mcp.github.com/sse"
        assert presets["github"].allowed_tools == ["search_issues"]
        assert presets["github"].defer_loading is True

    def test_load_file_json(self, monkeypatch, tmp_path):
        from discord_claude.config.mcp import load_anthropic_mcp_presets

        config_path = tmp_path / "anthropic_mcp.json"
        config_path.write_text(
            json.dumps({"calendar": {"url": "https://mcp.calendar.example/sse"}}),
            encoding="utf-8",
        )
        monkeypatch.delenv("ANTHROPIC_MCP_PRESETS_JSON", raising=False)
        monkeypatch.setenv("ANTHROPIC_MCP_PRESETS_PATH", str(config_path))

        presets = load_anthropic_mcp_presets()

        assert presets["calendar"].server_url == "https://mcp.calendar.example/sse"

    def test_invalid_schema_raises(self, monkeypatch):
        from discord_claude.config.mcp import load_anthropic_mcp_presets

        monkeypatch.setenv(
            "ANTHROPIC_MCP_PRESETS_JSON",
            json.dumps({"github": {"url": "not-a-url"}}),
        )
        monkeypatch.delenv("ANTHROPIC_MCP_PRESETS_PATH", raising=False)

        with pytest.raises(ValueError, match="valid HTTPS `url`"):
            load_anthropic_mcp_presets()

    def test_missing_auth_env_marks_preset_unavailable(self, monkeypatch):
        from discord_claude.config.mcp import load_anthropic_mcp_presets

        monkeypatch.setenv(
            "ANTHROPIC_MCP_PRESETS_JSON",
            json.dumps(
                {
                    "github": {
                        "url": "https://mcp.github.com/sse",
                        "authorization_env_var": "MISSING_TOKEN",
                    }
                }
            ),
        )
        monkeypatch.delenv("ANTHROPIC_MCP_PRESETS_PATH", raising=False)
        monkeypatch.delenv("MISSING_TOKEN", raising=False)

        presets = load_anthropic_mcp_presets()

        assert presets["github"].available is False
        assert "MISSING_TOKEN" in (presets["github"].unavailable_reason or "")
