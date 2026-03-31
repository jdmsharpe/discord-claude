from discord import Bot, Intents

from discord_claude import ClaudeCog


def test_package_import_registers_cog():
    bot = Bot(intents=Intents.default())
    bot.add_cog(ClaudeCog(bot=bot))
    assert bot.get_cog("ClaudeCog") is not None
