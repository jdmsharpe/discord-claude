from contextlib import contextmanager
import importlib
import sys


@contextmanager
def _fresh_package(prefix: str):
    original_modules = {
        name: module
        for name, module in list(sys.modules.items())
        if name == prefix or name.startswith(f"{prefix}.")
    }

    for name in original_modules:
        sys.modules.pop(name, None)

    try:
        yield
    finally:
        for name in list(sys.modules):
            if name == prefix or name.startswith(f"{prefix}."):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)


def test_top_level_package_import_is_lazy():
    with _fresh_package("discord_claude"):
        package = importlib.import_module("discord_claude")

        assert "discord_claude.cogs.claude.cog" not in sys.modules
        assert "ClaudeCog" in package.__all__


def test_cog_package_import_is_lazy():
    with _fresh_package("discord_claude"):
        package = importlib.import_module("discord_claude.cogs.claude")

        assert "discord_claude.cogs.claude.cog" not in sys.modules
        assert "ClaudeCog" in package.__all__
