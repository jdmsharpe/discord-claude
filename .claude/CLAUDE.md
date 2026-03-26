# Discord Claude Bot

Discord bot wrapping Anthropic's Claude API using py-cord.

## Architecture

- `src/bot.py` - Entry point; creates the Discord bot and loads the cog
- `src/anthropic_api.py` - Main cog: slash commands, conversation handling, tool call loop, `ParsedResponse` dataclass
- `src/util.py` - Constants, dataclasses (`ChatCompletionParameters`, `Conversation`, `UsageTotals`), `ToolHandler` Protocol, `ConversationKey` type, `available_embed_space()`, cost calculation
- `src/button_view.py` - Discord UI buttons and tool select menu
- `src/memory.py` - Client-side memory tool handler
- `src/bash_tool.py` - Client-side bash tool handler
- `src/config/auth.py` - `.env` loading via python-dotenv (`SHOW_COST_EMBEDS` toggles pricing embeds)
- `tests/` - pytest tests with mocked Discord and Anthropic clients

## Key Patterns

- **Model updates** — update four places:
  1. `src/anthropic_api.py` - `OptionChoice` list in the `chat` command's `model` option
  2. `src/util.py` - `ADAPTIVE_THINKING_MODELS` set (if the model supports adaptive thinking)
  3. `src/util.py` - `MODEL_CONTEXT_WINDOWS` dict (context window size for the model)
  4. `src/util.py` - `MODEL_PRICING` dict (per-million-token pricing)
- **Default model** — set in `chat()` signature and its `model` option description
- **Tool updates** — update five places:
  1. `src/util.py` - `AVAILABLE_TOOLS` dict with the tool definition
  2. `src/anthropic_api.py` - Add `@option` decorator (bool) and parameter to `chat()`, append to `enabled_tools`
  3. `src/button_view.py` - `SelectOption` in `_add_tool_select()`
  4. `src/memory.py` or new handler module — implement `ToolHandler` Protocol (`async execute(tool_input, user_id) -> str`)
  5. `src/anthropic_api.py` - Add handler class instance to `_tool_handlers` registry
- **Tool call flow** — `_call_api_with_tool_loop()`: uses `UsageTotals` for accumulation. `end_turn` = done, `pause_turn` = re-send, `tool_use` = execute via `_tool_handlers` registry (`ToolHandler` Protocol) and re-send. `COMPACTION_MODELS` use server-side compaction
- **Conversation keying** — conversations stored by `ConversationKey = (user_id, channel_id)` for O(1) lookup. `_build_api_params()` centralizes API parameter construction from `ChatCompletionParameters`
- **Context management** — 85% warning embed when approaching context window limit. Non-compaction models get automatic manual compaction at 75% via `_compact_conversation()` (uses Haiku for cheap summaries). `COMPACTION_MODELS` use server-side compaction instead
- **Context editing** — `context-management-2025-06-27` beta with `clear_thinking` (keeps last 2 turns) then `clear_tool_uses` (keeps last 5) edits. Thinking clearing must come before tool clearing
- **Prompt caching** — 1-hour TTL via `CACHE_TTL` for extended caching across Discord conversation pauses
- **Cost** — `calculate_cost()` handles cache write (2x), cache read (0.1x), and web search pricing. `_track_daily_cost()` emits structured `COST |` log lines
- **Embed ordering** — all embeds sent in one message, ButtonView attaches below. `_strip_previous_view()` removes buttons from previous turn
- **Multi-turn** — assistant messages stored as full `response.content` blocks to preserve encrypted server tool data for citations
- **Document citations** — PDF/text attachments sent as document blocks with citations enabled. Response citations distinguished by `kind` field (`"web"` vs `"document"`)

## Dependencies

- `anthropic` - Anthropic Python SDK (AsyncAnthropic client)
- `py-cord` - Discord API wrapper (slash commands, embeds, views)
- `python-dotenv` - Environment variable loading

## Testing

- `pytest` from project root — mocked Discord/Anthropic clients, no real API calls

## Type Checking

- `pyright src/` — Pyright configured via `pyrightconfig.json` (`basic` mode). Must pass with 0 errors before committing

## Style

Type hints, dataclasses, async/await, f-string logging
