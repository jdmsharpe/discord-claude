# Discord Claude Bot - Developer Reference

## Supported Entry Points

- Launcher: `python src/bot.py` remains supported and delegates to `discord_claude.bot.main`.
- Cog composition contract:

  ```python
  from discord_claude import ClaudeCog

  bot.add_cog(ClaudeCog(bot=bot))
  ```

  `ClaudeCog.__init__` calls `validate_required_config()` automatically, so config is validated at cog construction regardless of whether `main()` is used. Note: `GUILD_IDS` format is validated at import time (it is captured at class-definition time by `SlashCommandGroup`); `BOT_TOKEN` and `ANTHROPIC_API_KEY` missing or blank values are validated at construction time.
- `discord_claude` and `discord_claude.cogs.claude` both use lazy `__getattr__` exports so helper imports do not eagerly pull in Discord-heavy modules. Type-only imports keep `pyright src/` aware of those public exports.

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
            ├── tool_registry.py
            └── views.py
```

Only `src/bot.py` remains at the repo root; code imports should target `discord_claude...`.

## Testing And Patch Targets

- `pytest` runs with `pythonpath = ["src"]`.
- The test suite is organized into module-aligned files such as `tests/test_claude_cog.py`, `tests/test_claude_chat.py`, `tests/test_claude_client.py`, `tests/test_claude_tool_handlers.py`, `tests/test_config_auth.py`, `tests/test_tool_registry.py`, and `tests/test_lazy_imports.py`.
- MCP-specific coverage lives primarily in `tests/test_claude_mcp_config.py`, `tests/test_claude_request_config.py`, and the MCP cases in `tests/test_claude_chat.py`.
- `tests/test_package_import.py` is the package import smoke test.
- New tests and patches should target real owners under `discord_claude...`.
- Examples:
  - `discord_claude.memory.get_memories_base_dir`
  - `discord_claude.cogs.claude.attachments.SUPPORTED_IMAGE_TYPES`
  - `discord_claude.cogs.claude.client.AsyncAnthropic`
  - `discord_claude.cogs.claude.chat.call_api_with_tool_loop`
  - `discord_claude.config.mcp.ANTHROPIC_MCP_PRESETS`
  - `discord_claude.cogs.claude.chat.build_api_params`
  - `discord_claude.cogs.claude.tool_registry.TOOL_REGISTRY`
- Import `ClaudeCog` from `discord_claude`; do not reintroduce legacy `anthropic_api` shim paths.
- Auth config tests (`tests/test_config_auth.py`) use `importlib` to force a fresh module import per test. Because `load_dotenv()` runs at import time and restores values from the `.env` file, tests that control env state must suppress it: `monkeypatch.setattr("dotenv.load_dotenv", lambda *_, **__: None)`.

## Validation Commands

```bash
ruff check src/ tests/
ruff format src/ tests/
pyright src/
pytest -q
```

- The repo pre-commit hook prefers a repo-local `.venv` Ruff binary when available and falls back to `PATH`.

## Provider Notes

- Memory storage root is resolved via `discord_claude.cogs.claude.paths`.
- Tool metadata (Anthropic payload, UI label/description, execution mode) lives in `discord_claude.cogs.claude.tool_registry.TOOL_REGISTRY`. Adding a tool requires only a new `ToolRegistryEntry` there; `get_anthropic_tools` and `get_tool_select_options` derive the API and UI views automatically.
- Client-side tool dispatch lives in `ClaudeCog._execute_tool`, which looks up handlers in the per-cog `_tool_handlers` dict (initialized from `default_tool_handlers()` in `discord_claude.cogs.claude.tool_handlers`). The `memory` handler calls through `discord_claude.memory` so tests can patch the live owner. Use `cog.register_tool_handler(name, handler)` / `cog.unregister_tool_handler(name)` to extend or replace handlers at runtime.
- Conversations remain keyed by `(user_id, channel_id)`.
- Named MCP presets are loaded from `ANTHROPIC_MCP_PRESETS_JSON` (inline JSON) and/or `ANTHROPIC_MCP_PRESETS_PATH` (path to a JSON file); both are additive and duplicate preset names across them are rejected at startup.
- Claude MCP presets support only `url` (HTTPS), `authorization_env_var` (user-defined runtime token env var), `allowed_tools`, and `defer_loading` — no `kind` discriminator or approval loop.
- MCP state persists independently from built-in tool names via `mcp_preset_names` on `ChatCompletionParameters`.
- Anthropic MCP traffic is passed through with `mcp_servers` and `mcp_toolset`, and `call_api_with_tool_loop` adds the `mcp-client-2025-11-20` beta when MCP is active.
- MCP content blocks are ignored by the local tool loop; only built-in Anthropic tool calls are executed client-side.
