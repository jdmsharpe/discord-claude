# Discord Claude Bot

[![CI](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml/badge.svg)](https://github.com/jdmsharpe/discord-claude/actions/workflows/main.yml)

A Discord bot that wraps Anthropic's Claude API, providing an easy-to-use interface for conversing with Claude models directly in Discord.

## Features

- **Multi-turn conversations**: Start conversations with Claude that maintain context across multiple messages
- **Multiple Claude models**: Choose from Claude Opus 4.6, Sonnet 4.6, Opus 4.5, Sonnet 4.5, Opus 4.1, and Haiku 4.5
- **Multimodal input**: Attach images (JPEG, PNG, GIF, WEBP), PDFs, or text files (TXT, MD, CSV)
- **Tools**: Enable web search, web fetch, code execution, memory, and bash — toggleable mid-conversation
- **Citations**: Web search and document citations displayed as a separate Sources embed
- **Pricing display**: Per-request cost, token counts, and daily spend shown as a separate embed after each response (configurable via `SHOW_COST_EMBEDS`)
- **Conversation controls**: Pause, resume, regenerate responses, and end conversations with interactive buttons (previous turn's buttons are automatically removed)
- **System prompts**: Customize Claude's behavior with system prompts
- **Advanced parameters**: Fine-tune responses with temperature, top_p, top_k, effort, thinking budget, and max_tokens

## Commands

### `/claude chat`

Start a conversation with Claude.

**Parameters:**

- `prompt` (required): Your initial message to Claude
- `model`: Choose the Claude model (default: Claude Sonnet 4.6)
- `system`: System prompt to set Claude's behavior
- `attachment`: Attach an image (JPEG, PNG, GIF, WEBP), a PDF, or a text file (TXT, MD, CSV)
- `max_tokens`: Maximum tokens in the response (default: 16384)
- `web_search`: Enable web search for current information (default: false)
- `web_fetch`: Enable web fetch to retrieve full web page content (default: false)
- `code_execution`: Enable code execution in a sandbox (default: false)
- `memory`: Enable memory to save and recall information across conversations (default: false)
- `bash`: Enable bash to execute shell commands (default: false)
- `effort`: Control response effort — low (fast), medium (balanced), high (thorough)
- `thinking_budget`: Token budget for extended thinking on non-4.6 models
- `temperature`: Amount of randomness (0.0-1.0). Lower for analytical tasks, higher for creative (advanced)
- `top_p`: Nucleus sampling threshold (0.0-1.0). Use temperature OR top_p, not both (advanced)
- `top_k`: Only sample from top K tokens. Use temperature OR top_k, not both (advanced)

### `/claude check_permissions`

Check if the bot has the necessary permissions in the current channel.

## Setup

### Prerequisites

- Python 3.12+
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
   SHOW_COST_EMBEDS=true
   ```

### Running the Bot

**Directly:**

```bash
python src/bot.py
```

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
   - 🔧 Toggle tools on/off mid-conversation via the select menu

## License

MIT License - see [LICENSE](LICENSE) for details.
