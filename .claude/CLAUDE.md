# Discord Claude Bot - Developer Reference

## Supported Entry Points

- Launcher: `python src/bot.py` remains supported and delegates to `discord_claude.bot.main`.
- Cog composition contract:

  ```python
  from discord_claude import AnthropicAPI

  bot.add_cog(AnthropicAPI(bot=bot))
  ```

- Legacy shim: `src/anthropic_api.py` exists only for import compatibility and emits a `DeprecationWarning`.

## Package Layout

```text
src/
├── bot.py                           # Thin repo-local launcher
├── anthropic_api.py                 # Temporary compatibility shim
├── bash_tool.py                     # Top-level compatibility shim
├── memory.py                        # Top-level compatibility shim
├── util.py                          # Top-level compatibility shim
├── config/                          # Top-level compatibility shim
└── discord_claude/
    ├── __init__.py
    ├── bash_tool.py
    ├── bot.py
    ├── memory.py
    ├── util.py
    ├── config/
    │   ├── __init__.py
    │   └── auth.py
    └── cogs/claude/
        ├── __init__.py
        ├── client.py
        ├── cog.py
        ├── embeds.py
        ├── models.py
        ├── paths.py
        ├── tooling.py
        └── views.py
```

The namespaced `discord_claude.bash_tool` and `discord_claude.memory` modules are the real owners now. The top-level files are compatibility-only.

## Testing And Patch Targets

- `pytest` runs with `pythonpath = ["src"]`.
- New tests and patches should target real owners under `discord_claude...`, not `anthropic_api`, top-level `memory`, or top-level `bash_tool`.
- Examples:
  - `discord_claude.bash_tool.BASH_TIMEOUT`
  - `discord_claude.memory.MEMORIES_BASE_DIR`
  - `discord_claude.cogs.claude.cog.SUPPORTED_IMAGE_TYPES`
- `tests/test_namespace.py` is the shim/namespace smoke test.

## Validation Commands

```bash
ruff check src/ tests/
ruff format src/ tests/
pyright src/
pytest -q
```

## Provider Notes

- Memory storage root is resolved via `discord_claude.cogs.claude.paths`.
- Client-side tool dispatch in `discord_claude.cogs.claude.cog` should call through the namespaced `discord_claude.memory` and `discord_claude.bash_tool` modules so tests can patch the live owners.
- The bash runner prefers a real bash shell when available and normalizes `\r\n` to `\n` for consistent behavior across environments.
- Conversations remain keyed by `(user_id, channel_id)`.
