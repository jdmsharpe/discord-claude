from discord import Bot, Intents

from discord_claude import ClaudeCog


def test_namespaced_import_registers_cog(monkeypatch):
    intents = Intents.default()
    intents.presences = False
    intents.members = True
    intents.message_content = True
    intents.guilds = True
    bot = Bot(intents=intents)
    saved_add = bot.add_cog
    bot.add_cog = lambda cog: saved_add(cog)  # keep original behavior
    bot.add_cog(ClaudeCog(bot=bot))
    assert bot.get_cog("ClaudeCog") is not None
