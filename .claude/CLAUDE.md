# Discord Claude Bot

## Project Overview

A Discord bot wrapping Anthropic's Claude API using py-cord for Discord integration.

## Architecture

- `src/bot.py` - Entry point; creates the Discord bot and loads the cog
- `src/anthropic_api.py` - Main cog with slash commands (`/anthropic converse`, `/anthropic check_permissions`) and conversation handling
- `src/util.py` - Shared constants (`CLAUDE_MODELS`, `ADAPTIVE_THINKING_MODELS`), dataclasses (`ChatCompletionParameters`, `Conversation`), and helpers
- `src/button_view.py` - Discord UI buttons for conversation controls (regenerate, pause/resume, end)
- `src/config/auth.py` - Loads secrets from `.env` via python-dotenv
- `tests/` - pytest tests with mocked Discord and Anthropic clients

## Key Patterns

- **Model updates**: When adding a new Claude model, update three places:
  1. `src/anthropic_api.py` - `OptionChoice` list in the `converse` command's `model` option
  2. `src/util.py` - `CLAUDE_MODELS` list
  3. `src/util.py` - `ADAPTIVE_THINKING_MODELS` set (if the model supports adaptive thinking)
- **Adaptive thinking**: Models in `ADAPTIVE_THINKING_MODELS` get `thinking: {"type": "adaptive"}` in API calls
- **Default model**: Set in `converse()` function signature and described in the `model` option description

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
