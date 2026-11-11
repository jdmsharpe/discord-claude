<h1 align="center">Discord Claude Bot</h1>

<div align="center">

![Hits](https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fjdmsharpe%2Fdiscord-claude%2F&label=discord-claude&icon=github&color=%23198754&message=&style=flat&tz=UTC)
[![Version](https://img.shields.io/github/v/tag/jdmsharpe/discord-claude?sort=semver&label=version)](https://github.com/jdmsharpe/discord-claude/tags)
[![License](https://img.shields.io/github/license/jdmsharpe/discord-claude?label=license)](./LICENSE)
[![CI](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml/badge.svg)](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml)
[![Docker Pulls](https://img.shields.io/docker/pulls/jsgreen152/discord-claude?logo=docker&logoColor=white)](https://hub.docker.com/r/jsgreen152/discord-claude)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Codecov](https://codecov.io/gh/jdmsharpe/discord-claude/branch/main/graph/badge.svg)](https://app.codecov.io/gh/jdmsharpe/discord-claude)

</div>

## Overview

A Discord bot for Anthropic's Claude API, built on Pycord 2.0. It provides multi-turn Claude conversations through slash commands.

## Features

- **Chat:** Multi-turn conversations with Claude Fable 5.2 / 5.1 / 5, Opus 5.5 / 5 / 4.8 / 4.7 / 4.6 / 4.5, Sonnet 5.5 / 5 / 4.6 / 4.5 and Haiku 5.5 / 4.5. Messages you send in the channel continue the conversation.
- **Attachments:** Images (JPEG, PNG, GIF, WEBP), PDFs, and text or code files.
- **Reasoning:** Claude's summarized reasoning appears in a spoiler, or progress lines appear while tools run (`thinking_display`).
- **Built-in tools:** Web search, web fetch, code execution and memory.
- **Remote MCP:** Trusted servers enabled through named presets, with optional authorization, tool allow-lists and deferred tool loading.
- **Citations:** Web search and document citations appear in a Sources embed.
- **Refusal fallback (beta):** When the safety classifiers of Fable 5.2 / 5.1 / 5, Opus 5.5 / 5 or Sonnet 5.5 decline a request, the API retries it on a fallback model in the same request, and the reply says so.
- **Advisor (beta):** The model can consult a second Claude model for planning. Advisor calls are billed at the advisor model's rates; the cost line counts them, but its token counts cover only the main model.
- **Prompt caching and compaction:** Conversations are cached automatically. Long conversations are compacted server-side where the model supports it, and summarized by Claude Haiku 5.5 otherwise.
- **Cost line:** Each reply ends with a line such as `$0.0871 · 12.5k in (12.5k cached) / 405 out (80 thinking) · 2 searches · $0.09 today`: request cost, input tokens (cache reads in parentheses), output tokens (thinking in parentheses), tool and advisor calls and your total for the day. Set `SHOW_COST_EMBEDS=false` to hide it.

## Commands

### `/claude chat`

Start a conversation with Claude.

- **`prompt` (required):** Your first message.
- **`system`:** System prompt.
- **`model`:** Claude model (default: Claude Opus 5.5).
- **`attachment`:** An image, PDF, text or code file.
- **`max_tokens`:** Maximum response length in tokens (default: 16384).
- **`effort`:** `low`, `medium`, `high`, `xhigh` or `max`. Each model supports a subset, and an unsupported level is refused before the request is sent. When unset, the model's own default applies.
- **`fast`:** Faster responses on Opus 5.5 and Fable 5.2 at 2x token prices.
- **`thinking_budget`:** Thinking token budget for older models that use one.
- **`thinking_display`:** `summarized` (default) shows Claude's reasoning in a spoiler. `updates` (Fable 5.2 / 5.1 / 5, Opus 5.5, Sonnet 5.5) shows short progress lines while tools run instead.
- **`web_search` / `web_fetch` / `code_execution` / `memory`:** Enable built-in tools (default: off).
- **`advisor`:** Enable the advisor beta. The bot picks an advisor model the chosen model accepts; Opus 4.5 and Sonnet 4.5 can't use it.
- **`mcp`:** Comma-separated MCP preset names, active for the whole conversation (see [MCP Setup](#mcp-setup)).
- **`tool_choice`:** `auto` or `none` for enabled tools.

### `/claude effort`

Change the effort level of the active conversation in this channel for the messages that follow. The same per-model limits as `/claude chat` apply. On Fable 5.2 / 5.1, Opus 5.5 / 5, Sonnet 5.5 and Haiku 5.5 the prompt cache is kept; on other models the change invalidates it.

### `/claude check_permissions`

Check if the bot has the necessary permissions in the current channel.

## Setup & Installation

### Prerequisites

- Python 3.11+
- Discord Bot Token
- Anthropic API Key

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/jdmsharpe/discord-claude.git
   cd discord-claude
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package and its runtime dependencies:

   ```bash
   python -m pip install .
   ```

4. Copy the environment example file:

   ```bash
   cp .env.example .env
   ```

### Contributor Setup

Install development tooling for tests, linting, and type checking:

```bash
python -m pip install -e ".[dev]"
```

### Configuration (`.env`)

| Variable | Required | Description |
| --- | --- | --- |
| `BOT_TOKEN` | **Yes** | Your Discord bot token |
| `GUILD_IDS` | **Yes** | Comma-separated Discord server IDs |
| `ANTHROPIC_API_KEY` | **Yes** | Your Anthropic API key |
| `SHOW_COST_EMBEDS` | No | Show cost/spend embeds (`true`, `1`, or `yes` to enable) (Default: `true`) |
| `MEMORIES_DIR` | No | Directory for per-user memory files (Default: `./memories`) |
| `ANTHROPIC_MCP_PRESETS_JSON` | No | Inline JSON object of named MCP presets |
| `ANTHROPIC_MCP_PRESETS_PATH` | No | Path to a JSON file of named MCP presets |
| `CLAUDE_PRICING_PATH` | No | Path to a pricing YAML that overrides the bundled `src/discord_claude/config/pricing.yaml` |
| `LOG_FORMAT` | No | `text` (default) for human-readable logs, or `json` for structured JSON-lines output with per-request IDs |
| `SAFETY_IDENTIFIER_SECRET` | No | Key for the per-user identifier sent to Anthropic for abuse detection; must not equal `ANTHROPIC_API_KEY` (Default: derived from `BOT_TOKEN`) |

#### User Identifier

Every Messages API request the bot makes for a Discord user (chat turns, slash commands, follow-up messages and manual compaction summaries) carries a per-user identifier in `metadata.user_id` so Anthropic can attribute a policy violation to one Discord user instead of the whole bot.

- The identifier is an HMAC-SHA256 of the Discord user ID, keyed with `SAFETY_IDENTIFIER_SECRET` or, when that is unset, a key derived from `BOT_TOKEN`. Anthropic never receives the user ID or the key, and the bot refuses to start when `SAFETY_IDENTIFIER_SECRET` equals `ANTHROPIC_API_KEY`.
- Changing the key (or the bot token, when no secret is set) gives every user a new identifier. To keep identifiers stable across token changes, set the secret to a long random string, for example `python -c "import secrets; print(secrets.token_hex(32))"`.
- discord-claude, discord-grok, discord-openai and discord-openrouter compute it the same way, so a user gets the same identifier from each bot that shares the key.
- Memory tool errors name files by their `/memories/...` path, not by the on-disk path, which contains the Discord user ID.

#### MCP Setup

Configure named presets in `ANTHROPIC_MCP_PRESETS_JSON` or `ANTHROPIC_MCP_PRESETS_PATH`. Example:

```json
{
  "github": {
    "url": "https://api.githubcopilot.com/mcp/",
    "authorization_env_var": "GITHUB_MCP_TOKEN",
    "allowed_tools": ["search_issues"],
    "defer_loading": true
  }
}
```

A preset name defined in both sources is rejected. The opening embed of a conversation that uses MCP shows a safety note, and the presets stay active until the conversation ends.

Define presets only for servers you trust: the model can send conversation content to any server it calls.

### Running the Bot

**Locally:**

```bash
python src/bot.py
```

*(Note: `src/bot.py` is a thin launcher that delegates to `discord_claude.bot.main`)*

**With Docker:**

```bash
docker compose up -d --build
```

**Using as a Cog:**
To compose this repo into a larger bot, import the namespaced package:

```python
from discord_claude import ClaudeCog

bot.add_cog(ClaudeCog(bot=bot))
```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new application and add a bot in the "Bot" section.
3. Enable **Server Members Intent** and **Message Content Intent** under Privileged Gateway Intents.
4. Copy the bot token and add it to your `.env` file.
5. Go to OAuth2 > URL Generator.
6. Select scopes: `bot`, `applications.commands`.
7. Select permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`, `Embed Links`, `Attach Files`.
8. Use the generated URL to invite the bot to your server.

## Usage

1. Run `/claude chat` to start a conversation.
2. Send messages in the same channel to continue it.
3. Use the controls under each reply:
   - 🔄 Regenerate the last response
   - ⏯️ Pause or resume the conversation
   - ⏹️ End the conversation
   - **Tools** menu: turn tools on or off mid-conversation

## Development

### Testing

Tests use `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`). All tests are mocked (no real API calls).

```bash
# Install developer tooling if you have not already
python -m pip install -e ".[dev]"

# Run tests locally
python -m pytest -q

# Run tests in Docker
docker build --build-arg PYTHON_VERSION=3.11 -f Dockerfile.test -t discord-claude-test:3.11 .
docker run --rm discord-claude-test:3.11 python -m pytest -q

# Run linting and type checks in Docker
docker run --rm discord-claude-test:3.11 sh -lc 'ruff check src tests && ruff format --check src tests && pyright'
```

### Linting & Type Checking

```bash
ruff check src tests
ruff format --check src tests
pyright
```

*Run `git config core.hooksPath .githooks` after cloning to enable the pre-commit hook.*

## License

MIT License - see [LICENSE](LICENSE) for details.
