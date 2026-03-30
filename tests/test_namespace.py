import warnings

from discord import Bot, Intents

from discord_claude import AnthropicAPI


def test_namespaced_import_registers_cog(monkeypatch):
    intents = Intents.default()
    intents.presences = False
    intents.members = True
    intents.message_content = True
    intents.guilds = True
    bot = Bot(intents=intents)
    saved_add = bot.add_cog
    bot.add_cog = lambda cog: saved_add(cog)  # keep original behavior
    bot.add_cog(AnthropicAPI(bot=bot))
    assert bot.get_cog("AnthropicAPI") is not None


def test_legacy_shim_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import anthropic_api  # noqa: F401
    assert any("deprecated" in str(entry.message).lower() for entry in caught)
