import os

from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = ("BOT_TOKEN", "ANTHROPIC_API_KEY")


def _parse_guild_ids(raw_guild_ids: str) -> list[int]:
    guild_ids: list[int] = []

    for token in raw_guild_ids.split(","):
        stripped_token = token.strip()
        if not stripped_token:
            continue
        try:
            guild_ids.append(int(stripped_token))
        except ValueError as exc:
            raise RuntimeError(
                "Invalid GUILD_IDS value. Expected a comma-separated list of integers, "
                f"but received invalid token: {stripped_token!r}."
            ) from exc

    return guild_ids


def validate_required_config() -> None:
    missing_vars = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing_vars:
        missing_list = ", ".join(missing_vars)
        raise RuntimeError(
            "Missing required environment configuration: "
            f"{missing_list}. Please set these variables before starting the bot."
        )


BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILD_IDS = _parse_guild_ids(os.getenv("GUILD_IDS", ""))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SHOW_COST_EMBEDS = os.getenv("SHOW_COST_EMBEDS", "true").lower() == "true"
