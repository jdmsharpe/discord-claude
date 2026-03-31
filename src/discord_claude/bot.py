"""
Notes
---------------
May need to use this command to install pycord
python -m pip install --upgrade --no-deps --force-reinstall git+https://github.com/Pycord-Development/pycord
"""

from discord import Bot, Intents

from discord_claude import ClaudeCog
from discord_claude.config.auth import BOT_TOKEN


def main() -> None:
    intents = Intents.default()
    intents.presences = False
    intents.members = True
    intents.message_content = True
    intents.guilds = True
    bot = Bot(intents=intents)
    bot.add_cog(ClaudeCog(bot=bot))
    bot.run(BOT_TOKEN)


if __name__ == "__main__":
    main()
