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


def test_validate_required_config_rejects_whitespace_only_values(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "   ")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "\t")

    auth = _import_fresh_auth_module(monkeypatch)

    with pytest.raises(RuntimeError, match="BOT_TOKEN, ANTHROPIC_API_KEY"):
        auth.validate_required_config()


def test_invalid_guild_ids_raise_clear_error(monkeypatch):
    monkeypatch.setenv("GUILD_IDS", "123, abc, 456")

    with pytest.raises(RuntimeError, match="invalid token: 'abc'"):
        _import_fresh_auth_module()


def test_guild_ids_parsing_ignores_whitespace_and_empty_tokens(monkeypatch):
    monkeypatch.setenv("GUILD_IDS", " 123 , , 456 ,   ")

    auth = _import_fresh_auth_module()

    assert auth.GUILD_IDS == [123, 456]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
    ],
)
def test_show_cost_embeds_uses_standard_boolean_parser(monkeypatch, raw_value, expected):
    monkeypatch.setenv("SHOW_COST_EMBEDS", raw_value)

    auth = _import_fresh_auth_module()

    assert auth.SHOW_COST_EMBEDS is expected


def test_safety_identifier_secret_is_optional_and_stripped(monkeypatch):
    monkeypatch.setenv("SAFETY_IDENTIFIER_SECRET", "  operator-secret  ")

    auth = _import_fresh_auth_module(monkeypatch)

    assert auth.SAFETY_IDENTIFIER_SECRET == "operator-secret"
    auth.validate_required_config()


@pytest.mark.parametrize("raw_value", [None, "", "   "])
def test_unset_or_blank_safety_identifier_secret_is_none(monkeypatch, raw_value):
    if raw_value is None:
        monkeypatch.delenv("SAFETY_IDENTIFIER_SECRET", raising=False)
    else:
        monkeypatch.setenv("SAFETY_IDENTIFIER_SECRET", raw_value)

    auth = _import_fresh_auth_module(monkeypatch)

    assert auth.SAFETY_IDENTIFIER_SECRET is None


def test_validate_required_config_rejects_the_api_key_as_safety_secret(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "discord-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    monkeypatch.setenv("SAFETY_IDENTIFIER_SECRET", " dummy-key ")

    auth = _import_fresh_auth_module(monkeypatch)

    with pytest.raises(RuntimeError, match="must not equal ANTHROPIC_API_KEY") as exc_info:
        auth.validate_required_config()
    assert "dummy-key" not in str(exc_info.value)


@pytest.mark.parametrize("secret", ["separate-secret", None])
def test_validate_required_config_accepts_a_separate_or_absent_safety_secret(monkeypatch, secret):
    monkeypatch.setenv("BOT_TOKEN", "discord-token")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-key")
    if secret is None:
        monkeypatch.delenv("SAFETY_IDENTIFIER_SECRET", raising=False)
    else:
        monkeypatch.setenv("SAFETY_IDENTIFIER_SECRET", secret)

    auth = _import_fresh_auth_module(monkeypatch)

    auth.validate_required_config()
