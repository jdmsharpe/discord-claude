# Discord Claude Bot

![Badge](https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fjdmsharpe%2Fdiscord-claude%2F&label=discord-claude&icon=github&color=%23198754&message=&style=flat&tz=UTC)
[![CI](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml/badge.svg)](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)

A Discord bot that wraps Anthropic's Claude API, providing an easy-to-use interface for conversing with Claude models directly in Discord.

## Features

- **Multi-turn conversations**: Start conversations with Claude that maintain context across multiple messages
- **Multiple Claude models**: Choose from Claude Opus 4.6, Sonnet 4.6, Opus 4.5, Sonnet 4.5, Opus 4.1, and Haiku 4.5
- **Multimodal input**: Attach images (JPEG, PNG, GIF, WEBP), PDFs, or text files (TXT, MD, CSV)
- **Tools**: Enable web search, web fetch, code execution, and memory, with `tool_choice` control (`auto` / `none`) and mid-conversation toggles
- **MCP presets**: Enable trusted remote MCP servers per conversation through named presets loaded from config, with optional authorization env bindings, allow-lists, and deferred tool loading
- **Citations**: Web search and document citations displayed as a separate Sources embed
- **Prompt caching**: Automatic prompt caching reduces costs (cache reads at 10% of input price) and latency on multi-turn conversations
- **Context management**: Automatic compaction for non-compaction models at 75% context usage, server-side compaction for Opus/Sonnet 4.6, and an 85% context warning embed. Server-side clearing of old tool results and thinking blocks to manage context growth in long conversations
- **Pricing display**: Per-request cost, token counts, cache hits, and daily spend shown as a separate embed after each response (configurable via `SHOW_COST_EMBEDS`)
- **Conversation controls**: Pause, resume, regenerate responses, and end conversations with interactive buttons (previous turn's buttons are automatically removed)
- **System prompts**: Customize Claude's behavior with system prompts
- **Advanced parameters**: Fine-tune responses with temperature, top_p, top_k, effort, thinking budget, max_tokens, and tool behavior

## Commands

### `/claude chat`

Start a conversation with Claude.

**Parameters:**

- `prompt` (required): Your initial message to Claude
- `model`: Choose the Claude model (default: Claude Opus 4.6)
- `system`: System prompt to set Claude's behavior
- `attachment`: Attach an image (JPEG, PNG, GIF, WEBP), a PDF, or a text file (TXT, MD, CSV)
- `max_tokens`: Maximum tokens in the response (default: 16384)
- `web_search`: Enable web search for current information (default: false)
- `web_fetch`: Enable web fetch to retrieve full web page content (default: false)
- `code_execution`: Enable code execution in a sandbox (default: false)
- `memory`: Enable memory to save and recall information across conversations (default: false)
- `effort`: Control response effort — low (fast), medium (balanced), high (thorough)
- `thinking_budget`: Token budget for extended thinking on non-4.6 models
- `tool_choice`: Tool behavior for enabled tools (`auto` or `none`)
- `temperature`: Amount of randomness (0.0-1.0). Lower for analytical tasks, higher for creative (advanced)
- `top_p`: Nucleus sampling threshold (0.0-1.0). Use temperature OR top_p, not both (advanced)
- `top_k`: Only sample from top K tokens. Use temperature OR top_k, not both (advanced)
- `mcp`: Optional comma-separated MCP preset names. MCP presets persist for the life of the conversation and remain separate from the built-in tool dropdown.

### MCP Setup For `/claude chat`

Configure named presets in either `ANTHROPIC_MCP_PRESETS_JSON` or `ANTHROPIC_MCP_PRESETS_PATH`. Each preset is keyed by name and supports this schema:

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

- `url` must be HTTPS.
- `authorization_env_var` is optional. If it is set but missing at runtime, the preset is marked unavailable and the command returns a user-facing error instead of crashing the bot.
- `allowed_tools` should be used for least privilege when the server exposes many tools.
- `defer_loading` is passed through to Anthropic MCP server config.
- Anthropic MCP execution is server-side. The bot does not implement a Discord approval loop here; tool execution is controlled by Anthropic’s MCP connector flow and preset selection.

### `/claude check_permissions`

Check if the bot has the necessary permissions in the current channel.

## Setup

### Prerequisites

- Python 3.10+
- Discord Bot Token
- Anthropic API Key

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/discord-claude.git
   cd discord-claude
   ```

2. Create a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment example file and fill in your values:

   ```bash
   cp .env.example .env
   ```

5. Edit `.env` with your credentials:

   ```ini
  BOT_TOKEN=your_discord_bot_token
  GUILD_IDS=your_guild_id_1,your_guild_id_2
  ANTHROPIC_API_KEY=your_anthropic_api_key
  ANTHROPIC_MCP_PRESETS_JSON=optional_inline_json_object
  ANTHROPIC_MCP_PRESETS_PATH=optional_path_to_mcp_presets.json
  SHOW_COST_EMBEDS=true
  ```

### Running the Bot

**Directly:**

```bash
python src/bot.py
```

`src/bot.py` remains a thin repo-local launcher that delegates to `discord_claude.bot.main`.

### Using as a Cog

To compose this repo into a larger bot, import the namespaced package:

```python
from discord_claude import ClaudeCog

bot.add_cog(ClaudeCog(bot=bot))
```

Only `src/bot.py` remains at the repository root as a thin launcher; package code should be imported from `discord_claude`.

**With Docker:**

```bash
docker-compose up -d
```

## Discord Bot Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to the "Bot" section and create a bot
4. Enable the following Privileged Gateway Intents:
   - Server Members Intent
   - Message Content Intent
5. Copy the bot token and add it to your `.env` file
6. Go to OAuth2 > URL Generator
7. Select scopes: `bot`, `applications.commands`
8. Select permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`, `Embed Links`, `Attach Files`
9. Use the generated URL to invite the bot to your server

## Usage

1. Use `/claude chat` to start a conversation with Claude
2. Once a conversation is started, simply type messages in the same channel to continue the conversation
3. Use the interactive controls:
   - 🔄 Regenerate the last response
   - ⏯️ Pause/resume the conversation
   - ⏹️ End the conversation
   - 🔧 Toggle built-in tools mid-conversation via the select menu; clearing all built-in selections sets tool behavior to `none` only when no MCP presets are active
4. If MCP presets are enabled, the bot adds an explicit MCP safety note to the opening embeds and keeps those presets active for follow-up turns until the conversation ends

## Development

### Testing

Tests use pytest with pytest-asyncio (`asyncio_mode = "auto"`). All tests are mocked — no real API calls.
The suite is organized around the refactored package layout, with focused files such as `tests/test_claude_cog.py`, `tests/test_claude_chat.py`, `tests/test_claude_client.py`, `tests/test_claude_tool_handlers.py`, `tests/test_claude_mcp_config.py`, and `tests/test_claude_request_config.py`.
`tests/test_package_import.py` is the package import smoke test.
Import from `discord_claude` directly; legacy top-level shim modules are no longer part of the supported workflow.

GitHub Actions runs the test suite against Python 3.10, 3.11, 3.12, and 3.13. Docker images default to Python 3.13, but both `Dockerfile` and `Dockerfile.test` accept a `PYTHON_VERSION` build argument.

```bash
# Run tests
.venv/Scripts/python.exe -m pytest -q    # Windows
.venv/bin/python -m pytest -q            # Unix

# Run tests in Docker
docker build --build-arg PYTHON_VERSION=3.10 -f Dockerfile.test -t discord-claude-test:3.10 .
docker run --rm discord-claude-test:3.10
```

### Linting & Type Checking

```bash
ruff check src/ tests/
ruff format src/ tests/
pyright src/
```

After cloning, run `git config core.hooksPath .githooks` to enable the pre-commit hook.

## License

MIT License - see [LICENSE](LICENSE) for details.
