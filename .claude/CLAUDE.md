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
├── util.py                          # Repo-local helper
├── config/                          # Repo-local helper
└── discord_claude/
    ├── __init__.py
    ├── bot.py
    ├── memory.py
    ├── util.py
    ├── config/
    │   ├── __init__.py
    │   └── auth.py
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

## Testing And Patch Targets

- `pytest` runs with `pythonpath = ["src"]`.
- The test suite is organized into module-aligned files such as `tests/test_claude_cog.py`, `tests/test_claude_chat.py`, `tests/test_claude_client.py`, and `tests/test_claude_tool_handlers.py`.
- `tests/test_package_import.py` is the package import smoke test.
- New tests and patches should target real owners under `discord_claude...`.
- Examples:
  - `discord_claude.memory.MEMORIES_BASE_DIR`
  - `discord_claude.cogs.claude.attachments.SUPPORTED_IMAGE_TYPES`
  - `discord_claude.cogs.claude.client.AsyncAnthropic`
  - `discord_claude.cogs.claude.chat.call_api_with_tool_loop`
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
