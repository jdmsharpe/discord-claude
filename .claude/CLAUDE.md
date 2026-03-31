# Discord Claude Bot - Developer Reference

## Supported Entry Points

- Launcher: `python src/bot.py` remains supported and delegates to `discord_claude.bot.main`.
- Cog composition contract:

  ```python
  from discord_claude import ClaudeCog

  bot.add_cog(ClaudeCog(bot=bot))
  ```

## Package Layout

```text
src/
├── bot.py                           # Thin repo-local launcher
└── discord_claude/
    ├── __init__.py
    ├── bot.py
    ├── memory.py
    ├── util.py
    ├── config/
    │   ├── __init__.py
    │   ├── auth.py
    │   └── mcp.py
    └── cogs/
        ├── __init__.py
        └── claude/
            ├── __init__.py
            ├── attachments.py
            ├── chat.py
            ├── client.py
            ├── cog.py
            ├── embeds.py
            ├── models.py
            ├── paths.py
            ├── responses.py
            ├── state.py
            ├── tool_handlers.py
            ├── tooling.py
            └── views.py
```

Only `src/bot.py` remains at the repo root; code imports should target `discord_claude...`.

## Testing And Patch Targets

- `pytest` runs with `pythonpath = ["src"]`.
- The test suite is organized into module-aligned files such as `tests/test_claude_cog.py`, `tests/test_claude_chat.py`, `tests/test_claude_client.py`, and `tests/test_claude_tool_handlers.py`.
- MCP-specific coverage lives primarily in `tests/test_claude_mcp_config.py`, `tests/test_claude_request_config.py`, and the MCP cases in `tests/test_claude_chat.py`.
- `tests/test_package_import.py` is the package import smoke test.
- New tests and patches should target real owners under `discord_claude...`.
- Examples:
  - `discord_claude.memory.MEMORIES_BASE_DIR`
  - `discord_claude.cogs.claude.attachments.SUPPORTED_IMAGE_TYPES`
  - `discord_claude.cogs.claude.client.AsyncAnthropic`
  - `discord_claude.cogs.claude.chat.call_api_with_tool_loop`
  - `discord_claude.config.mcp.ANTHROPIC_MCP_PRESETS`
  - `discord_claude.cogs.claude.chat.build_api_params`
- Import `ClaudeCog` from `discord_claude`; do not reintroduce legacy `anthropic_api` shim paths.

## Validation Commands

```bash
ruff check src/ tests/
ruff format src/ tests/
pyright src/
pytest -q
```

## Provider Notes

- Memory storage root is resolved via `discord_claude.cogs.claude.paths`.
- Client-side tool dispatch lives in `discord_claude.cogs.claude.tooling`, which calls through `discord_claude.memory` so tests can patch the live owner.
- Conversations remain keyed by `(user_id, channel_id)`.
- Named MCP presets are loaded from `ANTHROPIC_MCP_PRESETS_JSON` and `ANTHROPIC_MCP_PRESETS_PATH`.
- MCP state persists independently from built-in tool names via `mcp_preset_names` on `ChatCompletionParameters`.
- Anthropic MCP traffic is passed through with `mcp_servers` and `mcp_toolset`, and `call_api_with_tool_loop` adds the `mcp-client-2025-11-20` beta when MCP is active.
- MCP content blocks are ignored by the local tool loop; only built-in Anthropic tool calls are executed client-side.
