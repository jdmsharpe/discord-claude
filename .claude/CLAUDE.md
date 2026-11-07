# Discord Claude Bot - Developer Reference

## Quick Start

```bash
uv sync --extra dev                   # creates .venv from uv.lock (no pip inside — use `uv pip` if needed)
cp .env.example .env                  # then fill in required values
git config core.hooksPath .githooks   # enable repo pre-commit hook
uv run python src/bot.py   # or: docker compose up --build
```

## Gotchas

- Uses **`py-cord`** (not `discord.py`). The slash-command API differs; don't mix docs between the two.
- `GUILD_IDS` must list at least one guild ID. Empty or unset parses to `[]`, and py-cord only registers a command globally when its `guild_ids is None`, so an empty list registers the commands **nowhere** — not globally, not per-guild. `validate_required_config()` does not check it, so the bot starts clean with no commands.

## Environment Variables

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | Yes | Discord bot token |
| `GUILD_IDS` | Yes | Comma-separated Discord server IDs; at least one is required — empty or unset registers no commands at all (not enforced at startup) |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `SHOW_COST_EMBEDS` | No | Show cost embeds (`true`/`1`/`yes`, default: `true`) |
| `MEMORIES_DIR` | No | Per-user memory directory (default: `./memories`) |
| `ANTHROPIC_MCP_PRESETS_JSON` | No | Inline JSON of named MCP presets |
| `ANTHROPIC_MCP_PRESETS_PATH` | No | Path to JSON file of named MCP presets |
| `CLAUDE_PRICING_PATH` | No | Override the bundled `src/discord_claude/config/pricing.yaml` |
| `LOG_FORMAT` | No | `text` (default) or `json` for structured JSON-lines output |
| `SAFETY_IDENTIFIER_SECRET` | No | Key for the per-user `metadata.user_id` identifier (default: a key derived from `BOT_TOKEN`; see Provider Notes); must not equal `ANTHROPIC_API_KEY` |

## Supported Entry Points

- Launcher: `python src/bot.py` remains supported and delegates to `discord_claude.bot.main`.
- Cog composition contract:

  ```python
  from discord_claude import ClaudeCog

  bot.add_cog(ClaudeCog(bot=bot))
  ```

  `ClaudeCog.__init__` calls `validate_required_config()` automatically, so config is validated at cog construction regardless of whether `main()` is used. Note: `GUILD_IDS` format is validated at import time (it is captured at class-definition time by `SlashCommandGroup`); `BOT_TOKEN` and `ANTHROPIC_API_KEY` missing or blank values, and a `SAFETY_IDENTIFIER_SECRET` equal to `ANTHROPIC_API_KEY`, are validated at construction time.
- `discord_claude` and `discord_claude.cogs.claude` both use lazy `__getattr__` exports so helper imports do not eagerly pull in Discord-heavy modules. Type-only imports keep `pyright src/` aware of those public exports.

## Package Layout

```text
src/
├── bot.py                           # Thin repo-local launcher
└── discord_claude/
    ├── __init__.py
    ├── bot.py
    ├── cost_line.py                 # One-line cost formatter, byte-identical across the discord-* AI bots (change all five together)
    ├── logging_setup.py             # Structured logging + request-id ContextVar
    ├── memory.py
    ├── stickers.py                  # Sticker-to-text labels for follow-ups, byte-identical across the discord-* AI bots (change all five together)
    ├── util.py
    ├── config/
    │   ├── __init__.py
    │   ├── auth.py
    │   ├── mcp.py
    │   ├── pricing.py                # YAML loader exposing MODEL_PRICING, MODEL_CONTEXT_WINDOWS, etc.
    │   └── pricing.yaml              # Canonical pricing data (override via CLAUDE_PRICING_PATH)
    └── cogs/
        ├── __init__.py
        └── claude/
            ├── __init__.py
            ├── attachments.py
            ├── chat.py
            ├── client.py
            ├── cog.py
            ├── command_options.py    # OptionChoice lists for slash-command menus
            ├── embed_delivery.py     # Embed batching (6000-char/10-embed caps) + plain-text fallback that re-sends files from saved bytes; byte-identical across the five AI bots
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
- The test suite is organized into module-aligned files such as `tests/test_claude_cog.py`, `tests/test_claude_chat.py`, `tests/test_claude_client.py`, `tests/test_claude_tool_handlers.py`, `tests/test_config_auth.py`, `tests/test_tool_registry.py`, `tests/test_lazy_imports.py`, `tests/test_claude_embeds.py`, `tests/test_claude_responses.py`, `tests/test_button_view.py`, `tests/test_memory.py`, and `tests/test_util.py`.
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
- A test that re-imports `discord_claude.util` must restore the original module afterwards (as `test_calculate_cost_uses_fallback_for_unknown_model` in `tests/test_config_pricing.py` does); otherwise later tests that patch `discord_claude.util` patch a different module object than the one the cog code imported.

## Validation Commands

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pyright src/
uv run pytest -q
```

- The repo pre-commit hook (`.githooks/pre-commit`) runs `ruff format` (auto-applied + re-staged), then `ruff check` (blocking), then `pyright` and `pytest --collect-only` as warning-only smoke tests. Resolves tools from `.venv/bin` or `.venv/Scripts` first, then `PATH`.

## Provider Notes

Probe results, dates, token counts and the history behind each bold-titled bullet are in [provider-history.md](provider-history.md) under the same title, together with the log of past SDK sweeps. Read the matching entry before changing that area; add new evidence there and keep each bullet here to the rule, the constants to keep aligned and the guarding tests.

- **SDK:** `anthropic~=2.6` (API version `2026-10-21`). 2.6.0 changed no signature, `Model` literal or usage type the bot uses; `OverloadedError` and `ServiceUnavailableError` now subclass `InternalServerError` (the bot catches neither), and a 504 is `GatewayTimeoutError`.
- Memory storage root is resolved via `discord_claude.cogs.claude.paths`.
- **Memory root guard:** the memory tool's `delete` and `rename` refuse the memory root (`/memories`, `/memories/`, `/memories/.`, `/memories/sub/..`, also with a relative `MEMORIES_DIR`), as the SDK memory helper does since anthropic 2.5.0; the refusal text names no path. Pinned by `TestMemoryRootGuard` in `tests/test_memory.py`.
- Tool metadata (Anthropic payload, UI label/description, execution mode) lives in `discord_claude.cogs.claude.tool_registry.TOOL_REGISTRY`. Adding a tool requires only a new `ToolRegistryEntry` there; `get_anthropic_tools` and `get_tool_select_options` derive the API and UI views automatically.
- Client-side tool dispatch lives in `ClaudeCog._execute_tool`, which looks up handlers in the per-cog `_tool_handlers` dict (initialized from `default_tool_handlers()` in `discord_claude.cogs.claude.tool_handlers`). The `memory` handler calls through `discord_claude.memory` so tests can patch the live owner. Use `cog.register_tool_handler(name, handler)` / `cog.unregister_tool_handler(name)` to extend or replace handlers at runtime.
- Conversations remain keyed by `(user_id, channel_id)`.
- **No sampling parameters:** API version `2026-10-21` removed `temperature`, `top_p` and `top_k`; the command, `ChatCompletionParameters` and the request builder no longer carry them for any model. Do not add them back. Wire tests check that no selectable model sends them.
- **Fast mode:** `/claude chat fast:true` is opt-in for Opus 5.5 and persists for the conversation. Requests send `speed="fast"` with no beta header; refusal fallbacks are sent at standard speed. Billing applies the 2x fast rate only to Opus 5.5 token and cache usage the response confirms as `usage.speed == "fast"` (`UsageTotals(request_speed=...)`), not to fallback models, advisor calls or flat tool fees.
- **Per-user identifier:** every Messages request made for a Discord user sends `metadata={"user_id": build_safety_identifier(user_id)}` (`util.py`). It is set once on `api_params` in `call_api_with_tool_loop` (`chat.py`), so both `beta.messages.create` and `messages.create` and every tool-loop iteration send it, and on the manual-compaction summarizer call (`compact_conversation(..., user_id=...)`, `state.py`). The value is `HMAC-SHA256(key, str(user_id).encode()).hexdigest()` (64 hex characters, sent untruncated; the API limit is 512). The key is `SAFETY_IDENTIFIER_SECRET` when set, otherwise `HMAC-SHA256(BOT_TOKEN, b"safety-identifier-v1")`; with neither, no `metadata` is sent. Never use `ANTHROPIC_API_KEY` as key material (`validate_required_config` rejects a secret equal to it), never send the raw ID or an unkeyed hash, and never log the key or the identifier. The construction, env var and label are shared with discord-openai, discord-openrouter and discord-grok; change all four together (`test_fixed_vectors_shared_with_sibling_bots`). Memory-tool error results go back to Anthropic as `tool_result`s, so `_without_user_dir` (`memory.py`) replaces the user directory with `/memories` in every error message. Guards: `tests/test_safety_identifier.py`, `TestSafetyIdentifier` / `TestDeriveSafetyIdentifierKey` (`tests/test_util.py`), the `SAFETY_IDENTIFIER_SECRET` cases in `tests/test_config_auth.py`, `TestErrorMessagesOmitUserId` (`tests/test_memory.py`).
- Named MCP presets are loaded from `ANTHROPIC_MCP_PRESETS_JSON` (inline JSON) and/or `ANTHROPIC_MCP_PRESETS_PATH` (path to a JSON file); both are additive and duplicate preset names across them are rejected at startup.
- Claude MCP presets support only `url` (HTTPS), `authorization_env_var` (user-defined runtime token env var), `allowed_tools`, and `defer_loading` — no `kind` discriminator or approval loop.
- MCP state persists independently from built-in tool names via `mcp_preset_names` on `ChatCompletionParameters`.
- Anthropic MCP traffic is passed through with `mcp_servers` and `mcp_toolset`, and `call_api_with_tool_loop` adds the `mcp-client-2025-11-20` beta when MCP is active.
- MCP content blocks are ignored by the local tool loop; only built-in Anthropic tool calls are executed client-side.
- **Future migration target:** the SDK now ships `client.beta.messages.tool_runner` with `anthropic.lib.tools.mcp.async_mcp_tool` for first-class MCP integration. Once that surface is GA-promoted out of `beta`, retire the manual `mcp-client-2025-11-20` beta-header path in `call_api_with_tool_loop`. (Last checked anthropic 2.6.0 on 2026-11-06 by introspecting the installed SDK — still beta-only: `client.messages.tool_runner` does not exist on `Anthropic` or `AsyncAnthropic`, only `client.beta.messages.tool_runner`; `anthropic.lib.tools.mcp` still defines `async_mcp_tool` but importing it raises ImportError without the `anthropic[mcp]` extra. Recheck on next anthropic SDK minor bump.)
- **Refusal fallback:** for each key of `REFUSAL_FALLBACK_TARGETS` (`util.py`; `REFUSAL_FALLBACK_MODELS` is its key set), `call_api_with_tool_loop` adds the `server-side-fallback-2026-06-01` beta and `fallbacks=[{"model": target}]`: Fable 5.1, Fable 5, Opus 5.5 and Opus 5 → `claude-opus-4-8`; Sonnet 5.5 → `claude-sonnet-5` (its only accepted target). Haiku 5.5 has classifiers but returns 400 for any `fallbacks`, so it is not a key. The `fallbacks="default"` routing mode is not adopted. Served-by detection reads `usage.iterations` for a `fallback_message` entry and sets `ParsedResponse.served_model`; `append_fallback_embed` shows a notice and `extract_response_content` skips `fallback` blocks. Billing: `UsageTotals.accumulate` groups each `message` / `fallback_message` entry under the model it names (`tokens_by_model`), and `track_daily_cost` bills each group at its own rates via `priced_model` (an id without a pricing row resolves to the request model). Every declined attempt is billed, because iteration usage has no stop reason or refusal category (`BetaMessageIterationUsage`, rechecked on anthropic 2.6.0); that is correct for `bio`, `frontier_llm` and `reasoning_extraction` refusals and over-bills the other categories. The client-side `BetaRefusalFallbackMiddleware` is deliberately not used. Guards: `TestTrackDailyCost` (`tests/test_claude_state.py`), `test_refusal_fallback_*` / `test_model_without_fallback_support_sends_no_fallback` / `test_sonnet_5_5_fallback_bills_the_sonnet_5_answer_at_sonnet_5_rates` (`tests/test_claude_chat.py`), `test_accumulate_fallback_message_iterations` / `test_refusal_fallback_models_are_the_classifier_models` (`tests/test_util.py`).
- **Per-model effort gate:** `output_config.effort` support differs by model and unsupported combinations return 400. `util.py` holds `EFFORT_MODELS` (every selectable model except `claude-sonnet-4-5` / `claude-haiku-4-5`), `XHIGH_EFFORT_MODELS` (Fable 5.1, Fable 5, Opus 5.5, Opus 5, Sonnet 5.5, Sonnet 5, Haiku 5.5, Opus 4.8, Opus 4.7 — the full `low`..`max` ladder) and `MAX_EFFORT_MODELS` (`XHIGH_EFFORT_MODELS` plus Opus 4.6 / Sonnet 4.6, which take `max` but not `xhigh`); `claude-opus-4-5` is in `EFFORT_MODELS` only (capped at `high`). `supported_effort_levels(model)` derives the accepted set and `validate_request_configuration` rejects anything else before dispatch. `RESPONSE_EFFORT_CHOICES` offers all five levels because slash-option choices cannot vary per model. An unset `effort` uses the model's default. Probe every level when adding a model. Guards: `TestModelCapabilitySets::test_effort_model_sets_membership` / `::test_every_chat_model_choice_has_an_effort_classification` (`tests/test_util.py`), `test_validate_request_configuration_*_effort_*` (`tests/test_claude_request_config.py`).
- **Programmatic-tool-calling gate:** `web_search_20260209` and `web_fetch_20260309` default `allowed_callers` to the code-execution caller, and `claude-haiku-4-5` lacks programmatic tool calling, so it returns 400 on that default. `PROGRAMMATIC_TOOL_CALLING_UNSUPPORTED_MODELS` (`util.py`) lists it, and `build_api_params` (`chat.py`) sends copies of the web tools with `allowed_callers: ["direct"]` for those models only (the registry dicts are not mutated). Guard: `TestProgrammaticToolCallingGate` (`tests/test_claude_request_config.py`).
- **Code-execution tool version:** `TOOL_REGISTRY["code_execution"]` sends `code_execution_20260521`. Next to `web_search_20260209` or `web_fetch_20260309` the API requires `code_execution_20260120` or later (older versions return 400 "Auto-injecting tools would conflict with existing tool names"). When a web tool version changes, check which code-execution version it requires. Guard: `tests/test_tool_registry.py::TestToolRegistry::test_tool_versions`.
- **Server-side compaction:** models in `COMPACTION_MODELS` (`util.py`: Fable 5.1, Fable 5, Opus 5.5, Opus 5, Sonnet 5.5, Sonnet 5, Haiku 5.5, Opus 4.8 / 4.7 / 4.6, Sonnet 4.6) send the `compact-2026-01-12` beta with a `compact_20260112` edit in `call_api_with_tool_loop`. The server's summarisation call is reported as `{"type": "compaction"}` entries in `usage.iterations` and excluded from top-level usage; `UsageTotals.accumulate` bills those entries and sets `context_compacted`. The on-demand top-level `compaction` parameter (`compact-2026-09-04`) cannot be combined with `context_management` and is not adopted.
  - Manual path (Opus 4.5, Sonnet 4.5, Haiku 4.5): when `UsageTotals.prompt_tokens` (input + cache-read + cache-write tokens of the latest response, read from the last `message` / `fallback_message` iteration when present) passes `manual_compaction_trigger(context_window)` — `CONTEXT_COMPACTION_THRESHOLD` (75%) of the smaller of the model window and the `COMPACTION_SUMMARY_MODEL` window — `compact_conversation` replaces the history with a summary. `compact_if_over_trigger` runs before each tool-loop follow-up request and after the final response. Haiku 5.5 counts about 30% more tokens than Haiku 4.5 for the same text, so the `min()` alone would not keep a 1M-window manual-path model under the summarizer's window.
  - Summarizer: `COMPACTION_SUMMARY_MODEL` is `claude-haiku-5-5`. `compact_conversation` calls `messages.create` with `output_config=SUMMARY_OUTPUT_CONFIG` (JSON schema of `ConversationSummary`) and `thinking={"type": "disabled"}` (Haiku 5.5 thinks by default and thinking counts against the call's 4096 `max_tokens`), with no effort, `fallbacks` or tools. It adds the usage to the turn (`accumulate_compaction_summary`, tiered by `long_context_applies`) and only then validates the text with `ConversationSummary.model_validate_json`; do not go back to `messages.parse`, which raises on invalid JSON and loses the usage. Thinking blocks in the history are sent to the summarizer unchanged; only advisor blocks are removed.
  - No summary, no compaction: a refusal, an empty or truncated response, or an `anthropic.APIError` leaves `messages` unchanged, logs a warning and returns None; `compact_if_over_trigger` sets `UsageTotals.compaction_failed`, does not retry in the same turn, and both reply paths show "Context Not Compacted".
  - Guards: `TestCompactConversation` / `TestCompactionSummaryUsage` (`tests/test_claude_state.py`); `test_manual_compaction_*`, `test_*_reports_a_compaction_that_did_not_happen`, `test_opus_5_uses_server_side_compaction` (`tests/test_claude_chat.py`); `TestModelCapabilitySets::test_manual_compaction_trigger_bounded_by_summarizer` / `::test_compaction_summary_model_is_haiku_5_5`, `test_accumulate_compaction_iterations` (`tests/test_util.py`).
- **Advisor pairs:** `ADVISOR_MODEL_COMPATIBILITY` (`util.py`) is the executor → advisor table from the advisor-tool docs (`ADVISOR_BETA` `advisor-tool-2026-03-01`, `ADVISOR_TOOL_TYPE` `advisor_20260301`), and the API accepts exactly its pairs. The `advisor` slash option is a toggle, so `get_default_advisor_model` (the first tuple entry) chooses the advisor and tuple order matters: `claude-opus-4-8` leads every tuple that allows it because it returns plaintext advice; the defaults are Opus 5 / Fable 5 → `claude-opus-5`, Opus 5.5 → `claude-opus-5-5`, Sonnet 5.5 → `claude-sonnet-5-5`, Haiku 5.5 → `claude-opus-4-8`, Fable 5.1 → Fable 5.1 only. Append new advisors at the end of a tuple so no default changes. Opus 5 / 5.5, Fable 5 / 5.1, Sonnet 5.5 and Haiku 5.5 advisors return an encrypted `advisor_redacted_result`; no extra handling is needed because `extract_response_content` and `_copy_messages_without_advisor_blocks` filter on the outer `advisor_tool_result` type. `claude-mythos-5` / `-5-1` are omitted (not publicly callable); `claude-sonnet-4-5` / `claude-opus-4-5` are not executors and `validate_request_configuration` rejects them. Guards: `test_advisor_model_compatibility_matches_accepted_pairs` / `test_default_advisor_model_prefers_plaintext_opus_4_8` (`tests/test_util.py`), `test_default_chat_model_has_an_advisor` (`tests/test_claude_cog.py`), `*_advisor_*` (`tests/test_claude_request_config.py`).
- **Claude Opus 5.5:** `claude-opus-5-5`, the `/claude chat` default. $4 / $20 per MTok; cache reads $0.20 (0.05x, declared as `cache_read_per_million` in `pricing.yaml`); 1h cache writes 2x; 1M context, 128K output. Adaptive thinking only (`enabled` and `disabled` return 400), sampling-locked, all five efforts (unset runs at `medium`), forced `tool_choice` returns 400, server-side compaction, per-message effort, `thinking.display: "updates"`, refusal fallback to Opus 4.8, programmatic tool calling, advisor executor and advisor. Guards: `TestModelCapabilitySets::test_opus_5_5_capability_membership` / `TestCalculateCost::test_opus_5_5_pricing` (`tests/test_util.py`), `tests/test_config_pricing.py`, `test_chat_command_default_model` (`tests/test_claude_cog.py`), the option-description guard.
- **Claude Sonnet 5.5:** `claude-sonnet-5-5`, menu option directly above Sonnet 5. $2 / $10 per MTok; cache reads $0.10 (0.05x, declared); 1h cache writes $4; 1M context, 128K output. Adaptive thinking is on by default and `disabled` / `budget_tokens` return 400, so it is in `ADAPTIVE_THINKING_MODELS` and `ADAPTIVE_ONLY_THINKING_MODELS`; its default `display` is `omitted`, and outside `ADAPTIVE_THINKING_MODELS` `build_thinking_config` would send no `display`. Sampling-locked, all five efforts, forced `tool_choice` returns 400 (`FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS`), per-message effort, `updates` display, compaction, programmatic tool calling, fallback target `claude-sonnet-5` only. Its thinking blocks are readable only by Opus 5.5; another model drops them without an error. Guards: `test_5_5_models_capability_membership` / `test_sonnet_5_5_only_capabilities` / `TestCalculateCost::test_sonnet_5_5_pricing` (`tests/test_util.py`), `tests/test_config_pricing.py`.
- **Claude Haiku 5.5:** `claude-haiku-5-5`, menu option directly above Haiku 4.5 and the `COMPACTION_SUMMARY_MODEL`. 1M context, 128K output, a tokenizer that counts about 30% more tokens than Haiku 4.5; two price tiers (see Prompt-length price tier). Adaptive thinking on by default with `display` `omitted` (in `ADAPTIVE_THINKING_MODELS`); `disabled` is accepted at effort `high` or below; `budget_tokens` returns 400 (`ADAPTIVE_ONLY_THINKING_MODELS`). Sampling-locked, all five efforts, per-message effort, compaction, programmatic tool calling. The API accepts forced `tool_choice` (it is not in `FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS`), but the bot's thinking-mode rule still refuses it and the menu offers only `auto` / `none`. No progress updates (not in `THINKING_DISPLAY_UPDATES_MODELS`); safety classifiers but no `fallbacks`; assistant prefill returns 400 (the bot never prefills). Guards: `test_5_5_models_capability_membership` / `test_sonnet_5_5_only_capabilities` and the tier tests.
- **Prompt-length price tier:** a `pricing.yaml` row may carry a `long_context` block (`threshold_tokens`, inclusive — Haiku 5.5 uses `100_001` because the higher prices start over 100,000 tokens — plus the tier's `input_per_million` / `output_per_million` and an optional `cache_read_per_million`), loaded into `LONG_CONTEXT_PRICING` (`config/pricing.py`) and applied by `long_context_applies(model, prompt_tokens)` and `calculate_cost(..., long_context=True)` (`util.py`). A prompt's length counts input, cache-read and cache-write tokens. The tier is chosen per sampling step: `UsageTotals._accumulate_executor_usage` measures each top-level usage object, or each `message` / `fallback_message` / `compaction` entry of `usage.iterations`, by its own prompt and adds it to `long_context_tokens_by_model` or `tokens_by_model`; `track_daily_cost` bills each group at its prices. Per-step tiering is inferred from Anthropic's docs, not stated for Haiku 5.5; the Admin API `cost_report` (`context_window` field) can confirm it. Haiku 5.5 requests always send `compact-2026-01-12`, which makes the API return `usage.iterations`. The summarizer call is tiered the same way; advisor usage is not tiered (Haiku 5.5 is never a default advisor). Guards: `TestCalculateCost::test_haiku_5_5_pricing_tiers` / `::test_long_context_applies_above_100_000_prompt_tokens`, `TestUsageTotals::test_price_tier_is_chosen_per_entry_from_its_own_prompt` / `::test_price_tier_boundary_is_inclusive_of_100_001` (`tests/test_util.py`), `test_haiku_5_5_price_tier_is_chosen_per_request` / `test_haiku_5_5_requests_send_the_compaction_beta` (`tests/test_claude_chat.py`), `TestTrackDailyCost::test_long_context_group_bills_at_the_tier_prices` (`tests/test_claude_state.py`), the `long_context` tests in `tests/test_config_pricing.py`.
- **Claude Sonnet 4.5 deprecation:** `claude-sonnet-4-5` retires on 2026-11-30T17:00Z (replacement `claude-sonnet-5-5`; the Models API reports `lifecycle: "deprecated"`). Remove its `CHAT_MODEL_CHOICES` entry and capability-set memberships before then and keep its `pricing.yaml` row. The SDK emits a `DeprecationWarning` on every Sonnet 4.5 call; it is log noise only, does not surface in tests (every API call there is an `AsyncMock`) and is not filtered.
- **Claude Fable 5.1:** `claude-fable-5-1`, menu option. $10 / $50 per MTok; cache reads $0.25 (0.025x, declared as `cache_read_per_million`, loaded into `CACHE_READ_PRICING` and read by `calculate_cost`; every row except Fable 5.1, Opus 5.5 and Sonnet 5.5 uses the derived 0.1x). Adaptive-only and sampling-locked; forced `tool_choice` (`any` / `tool`) returns 400, so it is in `FORCED_TOOL_CHOICE_UNSUPPORTED_MODELS` and `validate_request_configuration` refuses it with a model-specific message before the generic thinking rule. Its thinking blocks are readable only by Fable 5.1 or newer; for accounts created on or after 2026-08-31 the API returns 400 when anything before a Fable 5.1 thinking block changes between requests, so keep the replayed history append-only. Turn-scoped system messages are not adopted. Guards: `test_fable_5_1_cache_reads_bill_at_the_declared_quarter_rate` (`tests/test_util.py`), `test_cache_read_rate_is_declared_only_where_it_departs_from_the_default` (`tests/test_config_pricing.py`), `test_validate_request_configuration_rejects_forced_tool_use`.
- **Per-message effort:** `/claude effort` → `run_effort_command` → `apply_effort_change(conversation, level)` (`chat.py`) changes the effort for the caller's active conversation after the same `supported_effort_levels` gate as `/claude chat`. On `PER_MESSAGE_EFFORT_MODELS` (`util.py`: Fable 5.1, Opus 5.5, Opus 5, Sonnet 5.5, Haiku 5.5) it appends an effort-only `{"role": "system", "content": [], "output_config": {"effort": level}}` message (replacing a trailing one) and leaves the top-level `output_config.effort` unchanged, so the cached prompt prefix is preserved; other models change `params.effort` and the reply says the cache is invalidated. `call_api_with_tool_loop` sends `PER_MESSAGE_EFFORT_BETA` (`mid-conversation-output-config-2026-07-01`) on every request for these models from the first turn, because adding the header mid-conversation invalidates the prompt cache. Fable 5 rejects the override. `current_effort(conversation)` reports the effective level. Guards: `TestEffortChange`, `test_effort_override_message_sends_per_message_effort_beta`, `test_per_message_effort_models_send_the_beta_from_the_first_request`, `test_models_without_per_message_effort_do_not_send_the_beta` (`tests/test_claude_chat.py`), `test_effort_command_offers_the_full_effort_ladder` (`tests/test_claude_cog.py`).
- **Thinking display:** `ChatCompletionParameters.thinking_display` (`summarized` default, `THINKING_DISPLAY_CHOICES`) is the adaptive `display` value in `build_thinking_config`. `validate_request_configuration` allows `updates` only on `THINKING_DISPLAY_UPDATES_MODELS` (Fable 5.1, Fable 5, Opus 5.5, Sonnet 5.5). Under `updates`, `call_api_with_tool_loop` adds the `thinking-display-updates-2026-08-18` beta and, on each `tool_use` iteration, passes the response's text blocks and non-empty thinking blocks to the `progress_callback` that `make_progress_poster` builds, so users see status lines while tools run; the final thinking embed is empty in this mode. The option description and the `updates` choice label name "Fable, Opus/Sonnet 5.5" to stay within Discord's 100-character limit. Guards: `test_updates_display_posts_progress_and_sends_beta` / `test_summarized_display_posts_no_progress` (`tests/test_claude_chat.py`), `TestThinkingDisplay` (`tests/test_claude_request_config.py`), `test_thinking_display_choice_set` (`tests/test_claude_cog.py`).
- **Stickers are sent as text:** `handle_new_message_in_conversation` (`chat.py`) sends each sticker in `message.stickers` as a `[Sticker: <name>]` line after the message text, built by `text_with_stickers` in `stickers.py` (byte-identical in the five AI bots; change all five together). The sticker image is not sent. A follow-up with nothing to send is ignored and the conversation stays open. Guards: `tests/test_stickers.py` and the sticker follow-up tests in `tests/test_claude_chat.py`.

## Runtime Conventions (Cross-Project)

- **Pricing** is loaded from `src/discord_claude/config/pricing.yaml` by `config/pricing.py` at import time. Override via `CLAUDE_PRICING_PATH` to push a vendor price change without a code release. A row may add a `long_context` block for prompt-length price tiers (see "Prompt-length price tier"). Cross-referenced against [genai-prices/anthropic.yml](https://github.com/pydantic/genai-prices/blob/main/prices/providers/anthropic.yml).
- **Retry**: the `AsyncAnthropic` client is built with `max_retries=4, timeout=300` (total 5 attempts) in `client.py`; transient 429/5xx/connection errors recover transparently via the Anthropic SDK's built-in exponential backoff.
- **Conversation TTL**: `prune_runtime_state` in `cogs/claude/state.py` evicts conversations older than `CONVERSATION_TTL` (12h) every 15 minutes via `@tasks.loop`. Caps at `MAX_ACTIVE_CONVERSATIONS`. Daily costs retained for `DAILY_COST_RETENTION_DAYS` (30).
- **Request IDs**: `cog_before_invoke` (and `on_message`) bind a fresh 8-char hex id via `discord_claude.logging_setup.bind_request_id`. All downstream `logger.info`/`warning`/`error` calls automatically include the id. Set `LOG_FORMAT=json` for JSON-lines output.
- **Async file I/O**: blocking `open()` and `pathlib` methods (`read_bytes`, `write_bytes`, `unlink`, etc.) inside `async def` freeze the Discord event loop and stall every concurrent slash command. Wrap them with `asyncio.to_thread(...)` so the I/O runs on a worker thread. Enforced by `ruff` (`ASYNC230`/`ASYNC240`).
