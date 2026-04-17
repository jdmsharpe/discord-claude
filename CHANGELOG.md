# Changelog

## v1.1.0

### feat
- add `Conversation.touch()` and `updated_at` field; introduce `prune_runtime_state()` running on a `@tasks.loop(minutes=15)` that evicts conversations older than 12h, caps active conversations at 100, and retains `daily_costs` for 30 days (fixes unbounded runtime state accumulation)
- build `AsyncAnthropic` with `max_retries=4, timeout=300` (5 total attempts) so transient 429/5xx/connection errors recover transparently via the Anthropic SDK's built-in exponential backoff
- extract `MODEL_PRICING`, `MODEL_CONTEXT_WINDOWS`, and the web_search tool cost to `src/discord_claude/config/pricing.yaml`, loaded via `config/pricing.py`; override at runtime with the `CLAUDE_PRICING_PATH` env var so ops can push a vendor price change without a code release
- add `src/discord_claude/logging_setup.py` exposing `REQUEST_ID` (ContextVar), `bind_request_id()`, and `configure_logging()`; every slash command binds a fresh 8-char hex id via `cog_before_invoke` and `on_message` does the same, so all downstream `logger.info`/`warning`/`error` calls automatically include the id
- support `LOG_FORMAT=json` for JSON-lines log output suitable for log aggregators

### fix
- prevent memory leak from indefinitely accumulating conversation state by enforcing TTL and active-conversation caps in `prune_runtime_state()`

### chore
- bump project version to `1.1.0`
- add `PyYAML~=6.0` runtime dependency for the pricing loader
- adopt canonical `.githooks/pre-commit` across discord-* repos: `ruff format` (auto-applied + re-staged), `ruff check` (blocking), `pyright` (warning-only), and `pytest --collect-only` (warning-only smoke test)

### test
- add 6 pricing-loader tests covering YAML parsing and `CLAUDE_PRICING_PATH` override behavior
- add 5 conversation TTL/prune tests for `Conversation.touch()`, 12h eviction, 100-conversation cap, and 30-day daily-cost retention
- move `test_logging_setup` (8 tests) to the shared cross-repo pattern, covering request-id binding, JSON formatter, and ContextVar isolation
- total passing tests increases from 224 to 238

### docs
- refresh `README.md` with the new `CLAUDE_PRICING_PATH` and `LOG_FORMAT` env vars
- update `.claude/CLAUDE.md` with the retry, TTL, pricing-override, and request-id runtime conventions
- refresh `.env.example` with the new env vars

### compare
- [`v1.0.4...v1.1.0`](https://github.com/jdmsharpe/discord-claude/compare/v1.0.4...v1.1.0)
