import importlib
import sys

import pytest


MODULE_NAME = "discord_claude.config.auth"


def _import_fresh_auth_module(monkeypatch=None):
    sys.modules.pop(MODULE_NAME, None)
    if monkeypatch is not None:
        monkeypatch.setattr("dotenv.load_dotenv", lambda *_, **__: None)
    return importlib.import_module(MODULE_NAME)


def test_validate_required_config_reports_missing_vars(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    auth = _import_fresh_auth_module(monkeypatch)

    with pytest.raises(RuntimeError, match="BOT_TOKEN, ANTHROPIC_API_KEY"):
        auth.validate_required_config()


def test_validate_required_config_allows_present_vars(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "discord-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")

    auth = _import_fresh_auth_module()

    auth.validate_required_config()


def test_invalid_guild_ids_raise_clear_error(monkeypatch):
    monkeypatch.setenv("GUILD_IDS", "123, abc, 456")

    with pytest.raises(RuntimeError, match="invalid token: 'abc'"):
        _import_fresh_auth_module()


def test_guild_ids_parsing_ignores_whitespace_and_empty_tokens(monkeypatch):
    monkeypatch.setenv("GUILD_IDS", " 123 , , 456 ,   ")

    auth = _import_fresh_auth_module()

    assert auth.GUILD_IDS == [123, 456]
