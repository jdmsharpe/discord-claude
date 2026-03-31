# Discord Claude Bot - Developer Reference

## Supported Entry Points

- Launcher: `python src/bot.py` remains supported and delegates to `discord_claude.bot.main`.
- Cog composition contract:

  ```python
  from discord_claude import ClaudeCog

  bot.add_cog(ClaudeCog(bot=bot))
  ```

- Legacy shim: `src/anthropic_api.py` exists only for import compatibility and emits a `DeprecationWarning`.

## Package Layout

```text
src/
├── bot.py                           # Thin repo-local launcher
├── anthropic_api.py                 # Temporary compatibility shim
├── memory.py                        # Top-level compatibility shim
├── util.py                          # Top-level compatibility shim
├── config/                          # Top-level compatibility shim
└── discord_claude/
    ├── __init__.py
    ├── bot.py
    ├── memory.py
    ├── util.py
    ├── config/
    │   ├── __init__.py
    │   └── auth.py
    └── cogs/claude/
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

The namespaced `discord_claude.memory` module is the real owner now. The top-level file is compatibility-only.

## Testing And Patch Targets

- `pytest` runs with `pythonpath = ["src"]`.
- New tests and patches should target real owners under `discord_claude...`, not `anthropic_api` or top-level `memory`.
- Examples:
  - `discord_claude.memory.MEMORIES_BASE_DIR`
  - `discord_claude.cogs.claude.attachments.SUPPORTED_IMAGE_TYPES`
  - `discord_claude.cogs.claude.client.AsyncAnthropic`
  - `discord_claude.cogs.claude.chat.call_api_with_tool_loop`
- `tests/test_namespace.py` is the package import smoke test.
- `tests/test_anthropic_api_shim.py` is the legacy shim smoke test.

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
