# Discord Claude Bot

## Project Overview

A Discord bot wrapping Anthropic's Claude API using py-cord for Discord integration.

## Architecture

- `src/bot.py` - Entry point; creates the Discord bot and loads the cog
- `src/anthropic_api.py` - Main cog with slash commands (`/claude chat`, `/claude check_permissions`), conversation handling, and tool call loop
- `src/util.py` - Shared constants (`CLAUDE_MODELS`, `ADAPTIVE_THINKING_MODELS`, `COMPACTION_MODELS`, `AVAILABLE_TOOLS`), dataclasses (`ChatCompletionParameters`, `Conversation`), and helpers
- `src/button_view.py` - Discord UI buttons (regenerate, pause/resume, end) and tool Select Menu for mid-conversation tool toggling
- `src/memory.py` - Client-side memory tool handler (view, create, str_replace, insert, delete, rename)
- `src/bash_tool.py` - Client-side bash tool handler (execute shell commands with timeout and output truncation)
- `src/config/auth.py` - Loads secrets and config from `.env` via python-dotenv (`SHOW_COST_EMBEDS` toggles pricing embeds)
- `tests/` - pytest tests with mocked Discord and Anthropic clients

## Key Patterns

- **Model updates**: When adding a new Claude model, update three places:
  1. `src/anthropic_api.py` - `OptionChoice` list in the `chat` command's `model` option
  2. `src/util.py` - `CLAUDE_MODELS` list
  3. `src/util.py` - `ADAPTIVE_THINKING_MODELS` set (if the model supports adaptive thinking)
- **Adaptive thinking**: Models in `ADAPTIVE_THINKING_MODELS` get `thinking: {"type": "adaptive"}` in API calls
- **Default model**: Set in `chat()` function signature and described in the `model` option description
- **Tool updates**: When adding a new tool, update five places:
  1. `src/util.py` - `AVAILABLE_TOOLS` dict with the tool definition
  2. `src/anthropic_api.py` - Add `@option` decorator (bool) and parameter to `chat()`, append to `enabled_tools`
  3. `src/button_view.py` - `SelectOption` in `_add_tool_select()`
  4. `src/memory.py` or new handler module (for client-side tools)
  5. `src/anthropic_api.py` - `_execute_tool()` dispatch (for client-side tools)
- **Tool call flow**: `_call_api_with_tool_loop()` handles the response loop: `end_turn` = done, `pause_turn` = re-send to continue, `tool_use` = execute client-side tool and re-send. Models in `COMPACTION_MODELS` use the beta API with server-side compaction (`compact-2026-01-12`) to automatically summarize context when approaching limits
- **Auxiliary embeds**: Citations and cost embeds are sent as a separate message (`aux_embeds`) so the ButtonView stays attached to the response. On each new turn, `_strip_previous_view()` removes buttons from the previous turn's message via `last_view_messages` tracking
- **Multi-turn with tools**: Assistant messages are stored as full `response.content` blocks (not plain text) to preserve encrypted server tool data for citations across turns
- **Memory tool**: Client-side tool storing files in `./memories/{user_discord_id}/` with path traversal protection
- **Bash tool**: Client-side tool executing shell commands via `asyncio.create_subprocess_shell` with 30s timeout and 100-line output truncation
- **Document citations**: PDF and text file attachments are sent as document blocks with `citations: {enabled: true}`. Response citations use a `kind` field to distinguish types:
  - `kind: "web"` — web search citations with `url`, `title`, `cited_text`
  - `kind: "document"` — document citations with `cited_text`, `document_title`, `location` (page info for PDFs)

## Dependencies

- `anthropic` - Anthropic Python SDK (AsyncAnthropic client)
- `py-cord` - Discord API wrapper (slash commands, embeds, views)
- `python-dotenv` - Environment variable loading

## Testing

- Run tests: `pytest` from project root
- Tests use mocked Discord and Anthropic clients (see `tests/conftest.py`)
- No real API calls in tests

## Style

- Type hints throughout
- Dataclasses for structured state
- f-strings for logging
- Async/await for all I/O
