# Discord Claude Bot

![Hits](https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fjdmsharpe%2Fdiscord-claude%2F&label=discord-claude&icon=github&color=%23198754&message=&style=flat&tz=UTC)
[![Version](https://img.shields.io/github/v/tag/jdmsharpe/discord-claude?sort=semver&label=version)](https://github.com/jdmsharpe/discord-claude/tags)
[![License](https://img.shields.io/github/license/jdmsharpe/discord-claude?label=license)](./LICENSE)
[![CI](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml/badge.svg)](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)

## Overview

A Discord bot built on Pycord 2.0 that wraps Anthropic's Claude API, providing an easy-to-use interface for conversing with Claude models directly in Discord.

## Features

- **Multi-turn Conversations:** Start conversations with Claude that maintain context across multiple messages.
- **Multiple Claude Models:** Choose from Claude Opus (4.7, 4.6, 4.5, 4.1), Sonnet (4.6, 4.5), Haiku (4.5), and Claude Mythos Preview.
- **Multimodal Input:** Attach images (JPEG, PNG, GIF, WEBP), PDFs, or text files (TXT, MD, CSV).
- **Built-In Tools:** Enable web search, web fetch, code execution, and memory with `tool_choice` control (`auto` / `none`) and mid-conversation toggles.
- **Advisor Mode (Beta):** Enable Anthropic's advisor tool so supported executor models can consult Claude Opus 4.6 for higher-quality planning during complex tasks.
- **Remote MCP Support:** Enable trusted remote MCP servers per conversation through named presets, featuring optional authorization, allow-lists, and deferred tool loading.
- **Citations:** Web search and document citations are displayed as a separate Sources embed.
- **Prompt Caching:** Automatic prompt caching reduces costs (cache reads at 10% of input price) and latency on multi-turn conversations.
- **Context Management:** Automatic compaction for non-compaction models at 75% context usage, server-side compaction for Opus 4.7/4.6 and Sonnet 4.6, and an 85% context warning embed. Clears old tool results/thinking blocks to manage context growth when compatible.
- **Pricing Display:** Per-request cost, token counts, advisor-call counts, cache hits, and daily spend shown as a separate embed after each response (configurable).
- **Conversation Controls:** Pause, resume, regenerate responses, and end conversations with interactive buttons.
- **Customization:** Fine-tune responses with system prompts, temperature, top_p, top_k, effort, thinking budget, and max_tokens.

## Commands

### `/claude chat`

Start a conversation with Claude.

- **`prompt`** *(required)*: Your initial message to Claude.
- **`model`**: Choose the Claude model (default: Claude Opus 4.7).
- **`system`**: System prompt to set Claude's behavior.
- **`attachment`**: Attach an image, PDF, or text file.
- **`max_tokens`**: Maximum tokens in the response (default: 16384).
- **`web_search` / `web_fetch` / `code_execution` / `memory`**: Toggle individual tools (default: false).
- **`advisor`**: Enable Anthropic's advisor beta on supported executor models. Currently uses Claude Opus 4.6 as the advisor model.
- **`effort`**: Control response effort — low (fast), medium (balanced), high (thorough).
- **`thinking_budget`**: Token budget for legacy models that still support extended thinking budgets.
- **`tool_choice`**: Tool behavior for enabled tools (`auto` or `none`).
- **Advanced Tuning**: `temperature`, `top_p`, `top_k`.
- **`mcp`**: Optional comma-separated MCP preset names (persists for the life of the conversation).

### `/claude check_permissions`

Check if the bot has the necessary permissions in the current channel.

## Setup & Installation

### Prerequisites

- Python 3.10+
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

4. Configure your environment variables:

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

#### MCP Setup

Configure named presets in `ANTHROPIC_MCP_PRESETS_JSON` or `ANTHROPIC_MCP_PRESETS_PATH`. Duplicate names across both sources are rejected. Example schema:

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

### Using as a Cog

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

1. Use `/claude chat` to start a conversation.
2. Type messages in the same channel to continue the conversation seamlessly.
3. Use the interactive controls below the message to:
   - 🔄 Regenerate the last response
   - ⏯️ Pause/resume the conversation
   - ⏹️ End the conversation
   - 🔧 Toggle built-in tools mid-conversation via the select menu.
4. **Note on MCP:** If MCP presets are enabled, the bot adds an explicit MCP safety note to the opening embeds and keeps those presets active until the conversation ends.
5. **Note on Advisor:** Advisor guidance is billed separately at the advisor model's rates, so request cost can rise even when the executor model stays the same.
6. **Note on Mythos Preview:** Anthropic currently treats `claude-mythos-preview` as a restricted preview model, so access may depend on your Anthropic account or program enrollment.

## Development

### Testing

Tests use `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`). All tests are mocked (no real API calls).

```bash
# Install developer tooling if you have not already
python -m pip install -e ".[dev]"

# Run tests locally
python -m pytest -q

# Run tests in Docker
docker build --build-arg PYTHON_VERSION=3.10 -f Dockerfile.test -t discord-claude-test:3.10 .
docker run --rm discord-claude-test:3.10 python -m pytest -q

# Run linting and type checks in Docker
docker run --rm discord-claude-test:3.10 sh -lc 'ruff check src tests && ruff format --check src tests && pyright'
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
